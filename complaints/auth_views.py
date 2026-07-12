from django.contrib.auth import authenticate
from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile, DormitoryBuilding, Place, Role, RegistrationInvite
from .serializers import RegisterSerializer, DormitoryBuildingSerializer, PlaceSerializer
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


def _get_tokens_for_user(user):
    token = RefreshToken.for_user(user)
    token['email'] = user.email
    return {
        'access': str(token.access_token),
        'refresh': str(token),
    }


def _set_refresh_cookie(response, refresh_token):
    secure = not settings.DEBUG
    response.set_cookie(
        key='refresh_token',
        value=refresh_token,
        max_age=7 * 24 * 3600,
        httponly=True,
        secure=secure,
        samesite='Lax',
        path='/api/auth',
    )


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')

        if not email or not password:
            return Response(
                {'detail': 'Email and password are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=email, password=password)
        if user is None:
            return Response(
                {'detail': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user_profile = UserProfile.objects.filter(user=user).first()
        is_student = user_profile and user_profile.role and user_profile.role.role_name.lower() == 'student'
        if is_student:
            domain = email.split('@')[-1] if '@' in email else ''
            allowed = [d.strip().lower() for d in settings.ALLOWED_EMAIL_DOMAINS]
            if domain not in allowed:
                return Response(
                    {'detail': f'Email domain @{domain} is not authorized for student accounts'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        tokens = _get_tokens_for_user(user)
        response = Response({'access': tokens['access']}, status=status.HTTP_200_OK)
        _set_refresh_cookie(response, tokens['refresh'])
        return response


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = serializer.save()

            is_first_user = not UserProfile.objects.exists()

            if is_first_user:
                role, _ = Role.objects.get_or_create(role_name='admin')
                user.is_staff = True
                user.is_superuser = True
                user.save()
            else:
                role, _ = Role.objects.get_or_create(role_name='student')

            place = serializer.validated_data.get('place_id')

            UserProfile.objects.create(
                user=user,
                first_name=serializer.validated_data.get('first_name', ''),
                last_name=serializer.validated_data.get('last_name', ''),
                email=user.email,
                role=role,
                place_id=place,
            )

        tokens = _get_tokens_for_user(user)
        response = Response(
            {'access': tokens['access'], 'detail': 'Registration successful'},
            status=status.HTTP_201_CREATED,
        )
        _set_refresh_cookie(response, tokens['refresh'])
        return response


class CookieTokenRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get('refresh_token')
        if not refresh_token:
            return Response(
                {'detail': 'No refresh token'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            token = RefreshToken(refresh_token)
            token['email'] = token.payload.get('email', '')

            user_id = token.payload.get('user_id')
            try:
                user = User.objects.get(id=user_id)
                user_profile = UserProfile.objects.filter(user=user).first()
            except User.DoesNotExist:
                user_profile = None

            is_student = user_profile and user_profile.role and user_profile.role.role_name.lower() == 'student'
            if is_student:
                domain = (
                    token['email'].split('@')[-1].lower()
                    if '@' in token['email']
                    else ''
                )
                allowed = [d.strip().lower() for d in settings.ALLOWED_EMAIL_DOMAINS]
                if domain not in allowed:
                    return Response(
                        {'detail': 'Domain not authorized'},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

            response = Response(
                {'access': str(token.access_token)},
                status=status.HTTP_200_OK,
            )
            _set_refresh_cookie(response, str(token))
            return response
        except Exception:
            return Response(
                {'detail': 'Invalid or expired refresh token'},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class LogoutView(APIView):
    def post(self, request):
        response = Response(
            {'detail': 'Logged out'},
            status=status.HTTP_200_OK,
        )
        response.delete_cookie('refresh_token', path='/api/auth')
        return response


class BuildingListView(APIView):
    def get_authenticators(self):
        if self.request.method == 'POST':
            from .authentication import EmailDomainJWTAuthentication
            return [EmailDomainJWTAuthentication()]
        return []

    def get_permissions(self):
        if self.request.method == 'POST':
            from .permissions import IsCustomAdmin
            return [IsCustomAdmin()]
        return [AllowAny()]

    def get(self, request):
        buildings = DormitoryBuilding.objects.all().order_by('name')
        serializer = DormitoryBuildingSerializer(buildings, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = DormitoryBuildingSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PlaceListView(APIView):
    def get_authenticators(self):
        if self.request.method == 'POST':
            from .authentication import EmailDomainJWTAuthentication
            return [EmailDomainJWTAuthentication()]
        return []

    def get_permissions(self):
        if self.request.method == 'POST':
            from .permissions import IsCustomAdmin
            return [IsCustomAdmin()]
        return [AllowAny()]

    def get(self, request):
        building_id = request.query_params.get('building_id')
        if not building_id:
            return Response(
                {'detail': 'building_id query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        places = Place.objects.filter(
            building_id=building_id
        ).order_by('place_name')
        serializer = PlaceSerializer(places, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        building_id = request.data.get('building')
        place_name = request.data.get('place_name')
        if not building_id or not place_name:
            return Response(
                {'detail': 'building and place_name are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            building = DormitoryBuilding.objects.get(building_id=building_id)
        except DormitoryBuilding.DoesNotExist:
            return Response(
                {'detail': 'Building not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        if Place.objects.filter(building=building, place_name=place_name).exists():
            return Response(
                {'detail': 'Place with this name already exists in this building'},
                status=status.HTTP_400_BAD_REQUEST,
            )
            
        place = Place.objects.create(building=building, place_name=place_name)
        serializer = PlaceSerializer(place)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ChangePasswordView(APIView):
    def post(self, request):
        user = request.user
        old_password = request.data.get('old_password', '')
        new_password = request.data.get('new_password', '')

        if not old_password or not new_password:
            return Response(
                {'detail': 'old_password and new_password are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {'detail': 'New password must be at least 8 characters'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.check_password(old_password):
            return Response(
                {'detail': 'Old password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save()
        return Response({'detail': 'Password changed successfully'}, status=status.HTTP_200_OK)


class BuildingDetailView(APIView):
    def get_permissions(self):
        from .permissions import IsCustomAdmin
        return [IsCustomAdmin()]

    def patch(self, request, building_id):
        try:
            building = DormitoryBuilding.objects.get(building_id=building_id)
        except DormitoryBuilding.DoesNotExist:
            return Response(
                {'detail': 'Building not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = DormitoryBuildingSerializer(building, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InviteCreateView(APIView):
    def post(self, request):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile or not user_profile.role or user_profile.role.role_name.lower() not in ['admin', 'адміністратор']:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        
        role_name = request.data.get('role')
        if role_name not in ['admin', 'worker']:
            return Response({'detail': 'Invalid role type. Must be admin or worker.'}, status=status.HTTP_400_BAD_REQUEST)
        
        invite = RegistrationInvite.objects.create(
            role_name=role_name,
            created_by=user_profile
        )
        return Response({
            'token': invite.token,
            'role': invite.role_name,
            'is_used': invite.is_used
        }, status=status.HTTP_201_CREATED)


class InviteDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            invite = RegistrationInvite.objects.get(token=token)
        except (RegistrationInvite.DoesNotExist, ValueError, ValidationError):
            return Response({'detail': 'Invalid or expired invite link'}, status=status.HTTP_404_NOT_FOUND)
        
        if invite.is_used:
            return Response({'detail': 'This invite link has already been used'}, status=status.HTTP_400_BAD_REQUEST)
            
        return Response({
            'token': invite.token,
            'role': invite.role_name,
            'valid': True
        }, status=status.HTTP_200_OK)


class InviteRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, token):
        try:
            invite = RegistrationInvite.objects.get(token=token)
        except (RegistrationInvite.DoesNotExist, ValueError, ValidationError):
            return Response({'detail': 'Invalid or expired invite link'}, status=status.HTTP_404_NOT_FOUND)
        
        if invite.is_used:
            return Response({'detail': 'This invite link has already been used'}, status=status.HTTP_400_BAD_REQUEST)
        
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        confirm_password = request.data.get('confirm_password', '')
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()

        if not email or not password or not first_name or not last_name:
            return Response({'detail': 'All fields are required'}, status=status.HTTP_400_BAD_REQUEST)
            
        if password != confirm_password:
            return Response({'detail': 'Passwords do not match'}, status=status.HTTP_400_BAD_REQUEST)
            
        if len(password) < 8:
            return Response({'detail': 'Password must be at least 8 characters'}, status=status.HTTP_400_BAD_REQUEST)
            
        if User.objects.filter(email=email).exists():
            return Response({'detail': 'A user with this email already exists'}, status=status.HTTP_400_BAD_REQUEST)
            
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            
            role, _ = Role.objects.get_or_create(role_name=invite.role_name)
            if invite.role_name == 'admin':
                user.is_staff = True
                user.is_superuser = True
                user.save()
                
            UserProfile.objects.create(
                user=user,
                first_name=first_name,
                last_name=last_name,
                email=email,
                role=role
            )
            
            invite.is_used = True
            invite.save()
            
        tokens = _get_tokens_for_user(user)
        response = Response(
            {'access': tokens['access'], 'detail': 'Registration successful'},
            status=status.HTTP_201_CREATED,
        )
        _set_refresh_cookie(response, tokens['refresh'])
        return response

