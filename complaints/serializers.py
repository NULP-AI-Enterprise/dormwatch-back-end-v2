from django.contrib.auth.models import User
from django.conf import settings
from rest_framework import serializers
from .models import Complaint, UserProfile, Comment, DormitoryBuilding, Place, ComplaintCategory, Role, Ticket, Notification
from .image_utils import process_complaint_photo



class DormitoryBuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = DormitoryBuilding
        fields = ("building_id", "name", "address")


class PlaceSerializer(serializers.ModelSerializer):
    building = DormitoryBuildingSerializer()

    class Meta:
        model = Place
        fields = ("place_id", "place_name", "building")


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ("role_id", "role_name")


class UserSerializer(serializers.ModelSerializer):
    place = PlaceSerializer(read_only=True)
    role = RoleSerializer(read_only=True)
    class Meta:
        model = UserProfile
        fields = ['user', 'first_name', 'last_name', 'email', 'place', 'photo_url', 'role', 'contact_info']


class UpdateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['first_name', 'last_name', 'email', 'photo_url', 'contact_info']


class UpdateUserPlaceSerializer(serializers.Serializer):
    place_id = serializers.IntegerField()


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintCategory
        fields = ['name']


class UserComplaintSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['user', 'first_name', 'last_name', 'photo_url', 'contact_info']

class ComplaintSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    place = PlaceSerializer(read_only=True)
    user = UserComplaintSerializer(read_only=True)
    assigned_worker = serializers.SerializerMethodField()
    deadline = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        fields = ['complaint_id', 'user', 'title', 'description', 'category', 'status', 'photo_url', 'thumbnail', 'created_at', 'place', 'priority', 'photo_after', 'assigned_worker', 'deadline', 'comments_count']
        read_only_fields = ['complaint_id', 'created_at', 'user']

    def get_assigned_worker(self, obj):
        from .models import Ticket
        from .serializers import UserComplaintSerializer
        ticket = Ticket.objects.filter(complaint=obj).first()
        if ticket and ticket.user:
            return UserComplaintSerializer(ticket.user).data
        return None

    def get_deadline(self, obj):
        from .models import Ticket
        ticket = Ticket.objects.filter(complaint=obj).first()
        if ticket and ticket.deadline:
            return ticket.deadline.isoformat()
        return None

    def get_comments_count(self, obj):
        return obj.comment_set.count()

    def create(self, validated_data):
        uploaded_file = validated_data.pop('photo_url', None)
        if uploaded_file:
            result = process_complaint_photo(uploaded_file)
            validated_data['photo_url'] = result['full']
            validated_data['thumbnail'] = result['thumbnail']
        return super().create(validated_data)


class TicketSerializer(serializers.ModelSerializer):
    user = UserComplaintSerializer(read_only=True)
    complaint_detail = ComplaintSerializer(source='complaint', read_only=True)
    class Meta:
        model = Ticket
        fields = ['ticket_id', 'user', 'complaint', 'complaint_detail', 'deadline']


class UpdateUserRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['role']


class ComplaintStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = ['status', 'priority', 'photo_after']

    
class CommentSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_role = serializers.SerializerMethodField()
    class Meta:
        model = Comment
        fields = ['comment_id','complaint','user','user_name', 'user_role', 'description', 'created_at']
        read_only_fields = ("created_at", "user",'complaint')

    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip()

    def get_user_role(self, obj):
        return obj.user.role.role_name.lower() if (obj.user.role and obj.user.role.role_name) else 'student'


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=50, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=50, required=False, allow_blank=True)
    place_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_email(self, value):
        email = value.strip().lower()
        domain = email.split('@')[-1] if '@' in email else ''
        allowed = [d.strip().lower() for d in settings.ALLOWED_EMAIL_DOMAINS]
        if domain not in allowed:
            raise serializers.ValidationError(
                f'Email domain @{domain} is not authorized'
            )
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError('A user with this email already exists')
        return email

    def validate(self, data):
        if data.get('password') != data.get('confirm_password'):
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match'})
        return data

    def create(self, validated_data):
        email = validated_data['email']
        password = validated_data['password']
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        return user


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['notification_id', 'user', 'title', 'message', 'complaint', 'is_read', 'created_at']


class CampusStatusSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import CampusStatus
        model = CampusStatus
        fields = '__all__'


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import Announcement
        model = Announcement
        fields = '__all__'

