from django.shortcuts import render
from django.db.models import F
from rest_framework import generics, permissions, viewsets
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import Complaint, UserProfile, Comment, DormitoryBuilding, Place, ComplaintCategory, Role, Ticket, Notification
from .serializers import ComplaintSerializer, UpdateUserRoleSerializer, ComplaintStatusSerializer, CommentSerializer, UpdateUserSerializer, UserSerializer, UpdateUserPlaceSerializer, TicketSerializer, NotificationSerializer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .permissions import IsCustomAdmin, IsAdminOrCustomAdmin, IsAdminUser
from rest_framework import status


# Create your views here.

class ComplaintView(APIView):
    '''THIS VIEW IS FOR ADMIN AND OTHERS TO SEE'''
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    def get(self,request):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        is_admin = user_profile.role and user_profile.role.role_name.lower() in ['admin', 'адміністратор']
        
        complaints = Complaint.objects.all()
        if not is_admin:
            complaints = complaints.filter(status='published')
        category_param = request.query_params.get('category')
        status_param = request.query_params.get('status')
        corps_param = request.query_params.get('corps')
        priority_param = request.query_params.get('priority')
        if category_param:
            complaints = complaints.filter(category_id=category_param)
        if status_param:
            complaints = complaints.filter(status=status_param)
        if corps_param:
            complaints = complaints.filter(user__place__building__name=corps_param)
        if priority_param:
            complaints = complaints.filter(priority=priority_param)
        serializer = ComplaintSerializer(complaints, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class ComplaintDetailView(APIView):
    '''THIS VIEW IS FOR ADMIN AND OTHERS TO SEE ONE COMPLAINT'''
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    def get(self,request,complaint_id):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        is_admin = user_profile.role and user_profile.role.role_name.lower() in ['admin', 'адміністратор']
        
        try:
            complaint = Complaint.objects.get(complaint_id=complaint_id)
        except Complaint.DoesNotExist:
            return Response({'error': 'Complaint not found'}, status=status.HTTP_404_NOT_FOUND)
            
        if not is_admin and complaint.status != 'published' and complaint.user != user_profile:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        serializer = ComplaintSerializer(complaint)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserComplaintView(APIView):
    '''THIS VIEW IS FOR USER TO CREATE AND SEE ALL OF THEIR COMPLAINTS'''
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request):
        try:
            user_profile = request.user.profile
        except UserProfile.DoesNotExist:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        except AttributeError:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        complaints = Complaint.objects.filter(user=user_profile)
        serializer = ComplaintSerializer(complaints, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        place_id = request.data.get('place_id')
        place_name = request.data.get('place_name')
        category_name = request.data.get('category')
        category_obj = None
        target_place = None

        if place_name:
            building = None
            if user_profile.place and user_profile.place.building:
                building = user_profile.place.building
            else:
                building = DormitoryBuilding.objects.first()
            if building:
                target_place, _ = Place.objects.get_or_create(
                    building=building,
                    place_name=place_name
                )
                if not user_profile.place:
                    user_profile.place = target_place
                    user_profile.save()
        elif place_id:
            try:
                target_place = Place.objects.get(place_id=place_id)
            except Place.DoesNotExist:
                return Response({'error': 'Place not found.'}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({'error': f'Cannot find the place: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        elif user_profile.place:
            target_place = user_profile.place

        if category_name:
            category_obj, _ = ComplaintCategory.objects.get_or_create(name=category_name)
        else:
            return Response(
                {'error': 'Category name is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        data = request.data.copy()
        serializer = ComplaintSerializer(data=data)
        if serializer.is_valid():
            complaint = serializer.save(user=user_profile, place=target_place, category=category_obj)
            try:
                admins = UserProfile.objects.filter(role__role_name__in=['admin', 'адміністратор'])
                priority_labels = {
                    'low': 'низьким',
                    'medium': 'середнім',
                    'high': 'високим',
                    'critical': 'критичним'
                }
                priority_label = priority_labels.get(complaint.priority, complaint.priority)
                title = f"Нова скарга: {complaint.title}"
                message = f"З'явилася скарга з {priority_label} пріоритетом: {complaint.title}"
                for admin in admins:
                    Notification.objects.create(
                        user=admin,
                        title=title,
                        message=message,
                        complaint=complaint
                    )
            except Exception as e:
                print("Error creating admin notification:", e)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserComplaintDetailView(APIView):
    '''THIS VIEW IS FOR USER TO SEE ONE COMPLAINT AND ABILITY DELETE IT'''
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)
    def get(self, request, complaint_id):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            complaint = Complaint.objects.get(complaint_id=complaint_id, user=user_profile)
        except Complaint.DoesNotExist:
            return Response({'error': 'Complaint not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ComplaintSerializer(complaint)
        return Response(serializer.data, status=status.HTTP_200_OK)

    # def put(self, request, complaint_id):
    #     user_profile = UserProfile.objects.filter(user=request.user).first()
    #     if not user_profile:
    #         return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    #     try:
    #         complaint = Complaint.objects.get(complaint_id=complaint_id, user=user_profile)
    #     except Complaint.DoesNotExist:
    #         return Response({'error': 'Complaint not found'}, status=status.HTTP_404_NOT_FOUND)
    #     serializer = ComplaintSerializer(complaint, data=request.data)
    #     if serializer.is_valid():
    #         serializer.save()
    #         return Response(serializer.data, status=status.HTTP_200_OK)
    #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, complaint_id):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
            
        try:
            complaint = Complaint.objects.get(complaint_id=complaint_id)
        except Complaint.DoesNotExist:
            return Response({'error': 'Complaint not found'}, status=status.HTTP_404_NOT_FOUND)
            
        is_admin = user_profile.role and user_profile.role.role_name.lower() in ['admin', 'адміністратор']
        
        if complaint.user != user_profile and not is_admin:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        if is_admin and complaint.user != user_profile:
            try:
                title = f"Видалення скарги: {complaint.title}"
                message = f"Адмін видалив твою скаргу: '{complaint.title}'"
                Notification.objects.create(
                    user=complaint.user,
                    title=title,
                    message=message,
                    complaint=None
                )
            except Exception as e:
                print("Error creating delete notification:", e)

        complaint.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class UpdateUserRoleView(APIView):
    permission_classes = [IsAdminUser]
    def patch(self, request, user_id):
        try:
            user_profile = UserProfile.objects.get(user = user_id)
        except UserProfile.DoesNotExist:
            return Response({'error': 'User not found'}, status = status.HTTP_404_NOT_FOUND)
        
        serializer = UpdateUserRoleSerializer(
            user_profile,
            data = request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status = status.HTTP_200_OK)

        return Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)        
    

class UserProfileView(APIView):
    permission_classes=[IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)
    def get(self, request):
        try:
            user_profile = (
                UserProfile.objects
                .select_related("place__building")
                .get(user=request.user)
            )
        except UserProfile.DoesNotExist:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        except AttributeError:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        
        serializer = UserSerializer(user_profile)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def patch(self, request):
        try:
            user_profile = (
                UserProfile.objects
                .select_related("place__building")
                .get(user=request.user)
            )
        except UserProfile.DoesNotExist:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        except AttributeError:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        
        serializer = UpdateUserSerializer(user_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            user_profile.refresh_from_db()
            serializer = UserSerializer(user_profile)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request):
        user=request.user
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class AdminComplaintStatusView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def patch(self, request, complaint_id):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
            
        is_admin = user_profile.role and user_profile.role.role_name.lower() in ['admin', 'адміністратор']
        is_assigned_worker = Ticket.objects.filter(complaint_id=complaint_id, user=user_profile).exists()
        
        if not is_admin and not is_assigned_worker:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            complaint = Complaint.objects.get(complaint_id=complaint_id)
        except Complaint.DoesNotExist:
            return Response({'error': 'Complaint not found'}, status=status.HTTP_404_NOT_FOUND)
        
        old_status = complaint.status
        serializer = ComplaintStatusSerializer(
            complaint,
            data = request.data,
            partial = True
        )

        if serializer.is_valid():
            updated_complaint = serializer.save()
            if old_status != updated_complaint.status:
                try:
                    status_labels = {
                        'pending': 'Очікує',
                        'published': 'У роботі',
                        'denied': 'Відхилено',
                        'resolved': 'Вирішено'
                    }
                    status_label = status_labels.get(updated_complaint.status, updated_complaint.status)
                    
                    if updated_complaint.status == 'resolved':
                        title = "Заявку виконано! 🎉"
                        message = f"Майстер завершив ремонт за вашою заявкою '{updated_complaint.title}'. Будь ласка, перевірте результат та залиште відгук, якщо виникнуть питання."
                    elif updated_complaint.status == 'denied':
                        title = "Заявку відхилено ❌"
                        reason = updated_complaint.rejection_reason or ""
                        if reason:
                            message = f"Вашу заявку '{updated_complaint.title}' було відхилено. Причина: {reason}"
                        else:
                            message = f"Вашу заявку '{updated_complaint.title}' було відхилено."
                    else:
                        title = f"Оновлення статусу: {updated_complaint.title}"
                        message = f"Статус скарги змінено на: {status_label}"
                        
                    Notification.objects.create(
                        user=updated_complaint.user,
                        title=title,
                        message=message,
                        complaint=updated_complaint
                    )
                except Exception as e:
                    print("Error creating status change notification:", e)
            return Response(serializer.data, status = status.HTTP_200_OK)

        return Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)    


class CommentListView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, complaint_id):
       
        user_profile = UserProfile.objects.filter( user = request.user).first()

        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            complaint = Complaint.objects.get(complaint_id=complaint_id)
        except Complaint.DoesNotExist:
            return Response({'error': 'Complaint not found'}, status=status.HTTP_404_NOT_FOUND)
        

        serializer = CommentSerializer(data=request.data)
        if serializer.is_valid():
            is_admin = user_profile.role and user_profile.role.role_name.lower() in ['admin', 'адміністратор']
            is_creator = complaint.user == user_profile
            is_assigned_worker = Ticket.objects.filter(complaint=complaint, user=user_profile).exists()
            
            if not is_creator and not is_admin and not is_assigned_worker:
                return Response({'error': 'Permission denied'},status=status.HTTP_403_FORBIDDEN)
                
            serializer.save(user=user_profile, complaint_id=complaint_id)
            
            is_worker_user = user_profile.role and user_profile.role.role_name.lower() in ['worker', 'робітник', 'майстер']

            # Case A: Commented by a worker
            if is_worker_user:
                # Notify the student
                if complaint.user != user_profile:
                    try:
                        title = "Новий коментар до вашої скарги"
                        message = f"Працівник {user_profile.first_name} {user_profile.last_name} прокоментував вашу скаргу: '{complaint.title}'"
                        Notification.objects.create(
                            user=complaint.user,
                            title=title,
                            message=message,
                            complaint=complaint
                        )
                    except Exception as e:
                        print("Failed to notify student of worker comment:", e)



            # Case B: Commented by student or admin
            else:
                # Notify the student (if admin commented)
                if not is_creator:
                    try:
                        title = "Новий коментар до вашої скарги"
                        role_label = "Адміністратор" if is_admin else "Працівник"
                        message = f"{role_label} {user_profile.first_name} {user_profile.last_name} прокоментував вашу скаргу: '{complaint.title}'"
                        Notification.objects.create(
                            user=complaint.user,
                            title=title,
                            message=message,
                            complaint=complaint
                        )
                    except Exception as e:
                        print("Failed to create comment notification for student:", e)

                # Notify the assigned worker(s) if any
                assigned_tickets = Ticket.objects.filter(complaint=complaint).exclude(user=None)
                for t in assigned_tickets:
                    if t.user != user_profile:
                        try:
                            title = "Новий коментар до призначеної скарги"
                            role_label = "Адміністратор" if is_admin else "Користувач"
                            message = f"{role_label} {user_profile.first_name} {user_profile.last_name} прокоментував скаргу: '{complaint.title}'"
                            Notification.objects.create(
                                user=t.user,
                                title=title,
                                message=message,
                                complaint=complaint
                            )
                        except Exception as e:
                            print("Failed to notify worker of comment:", e)
                            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


    
    def get(self, request, complaint_id):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            complaint = Complaint.objects.get(complaint_id=complaint_id)
        except Complaint.DoesNotExist:
            return Response({'error': 'Complaint not found'}, status=status.HTTP_404_NOT_FOUND)
            
        is_admin = user_profile.role and user_profile.role.role_name.lower() in ['admin', 'адміністратор']
        is_creator = complaint.user == user_profile
        is_assigned_worker = Ticket.objects.filter(complaint=complaint, user=user_profile).exists()
        
        if not is_creator and not is_admin and not is_assigned_worker:
            return Response({'error': 'Permission denied'},status=status.HTTP_403_FORBIDDEN)
            
        comments =( Comment.objects
                   .filter(complaint_id=complaint_id)
                   .select_related("user")
                   .order_by("created_at")
                   )
        
        serializer = CommentSerializer(comments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class CommentDeleteView(APIView):
    permission_classes = [IsAuthenticated]
    def delete(self, request, comment_id):
       
        user_profile = UserProfile.objects.filter(user = request.user).first()
        
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            comment = Comment.objects.get(comment_id=comment_id)
        except Comment.DoesNotExist:
            return Response(
                {'error': 'Comment not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        is_admin = user_profile.role and user_profile.role.role_name.lower() in ['admin', 'адміністратор']
        if comment.user != user_profile and not is_admin:
            return Response({'error': 'Permission denied'},status=status.HTTP_403_FORBIDDEN)

        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TicketView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    def get(self,request):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
            
        is_admin = user_profile.role and user_profile.role.role_name.lower() in ['admin', 'адміністратор']
        is_worker = user_profile.role and user_profile.role.role_name.lower() == 'worker'
        
        if not is_admin and not is_worker:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            
        tickets = Ticket.objects.all()
        if is_worker:
            tickets = tickets.filter(user=user_profile)
            
            # Check for approaching deadlines (< 24 hours) for unresolved tickets
            from django.utils import timezone
            from datetime import timedelta
            now = timezone.now()
            tomorrow = now + timedelta(hours=24)
            approaching = tickets.filter(
                deadline__gt=now,
                deadline__lte=tomorrow,
                complaint__status__in=['pending', 'published', 'active']
            )
            for t in approaching:
                warning_title = "Наближається дедлайн ⏳"
                exists = Notification.objects.filter(
                    user=user_profile,
                    title=warning_title,
                    complaint=t.complaint
                ).exists()
                if not exists:
                    try:
                        Notification.objects.create(
                            user=user_profile,
                            title=warning_title,
                            message=f"Нагадування: термін виконання призначеної заявки '{t.complaint.title}' спливає менш ніж через 24 години! Будь ласка, оновіть статус роботи.",
                            complaint=t.complaint
                        )
                    except Exception as ne:
                        print("Error creating deadline warning notification:", ne)
        else:
            worker_param = request.query_params.get('worker')
            if worker_param:
                tickets = tickets.filter(user_id=worker_param)
                
        date_from_param = request.query_params.get('date_from')
        date_to_param = request.query_params.get('date_to')
        priority_param = request.query_params.get('priority')
        
        if priority_param:
            tickets = tickets.filter(complaint__priority=priority_param)
        if date_from_param:
            tickets = tickets.filter(deadline__gte=date_from_param)
        if date_to_param:
            tickets = tickets.filter(deadline__lte=date_to_param)
            
        serializer = TicketSerializer(tickets, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self,request):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        if not user_profile.role or user_profile.role.role_name.lower() not in ['admin', 'адміністратор']:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        complaint_id = request.data.get('complaint')
        worker_id = request.data.get('user')
        target_complaint = None
        target_worker = None

        if complaint_id:
            try:
                target_complaint = Complaint.objects.get(complaint_id=complaint_id)
            except Complaint.DoesNotExist:
                return Response({'error': 'Complaint not found.'}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({'error': f'Cannot find the complaint: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(
                {"error": "complaint_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if worker_id:
            try:
                target_worker=UserProfile.objects.get(user_id=worker_id)
                if not target_worker.role or target_worker.role.role_name.lower() != 'worker':
                    return Response({'error': 'User is not a worker'}, status=status.HTTP_400_BAD_REQUEST)
            except UserProfile.DoesNotExist:
                return Response({'error': 'Worker not found'}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({'error': f'Cannot find the worker: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
        data = request.data.copy()
        serializer = TicketSerializer(data=data)
        if serializer.is_valid():
            ticket = serializer.save(complaint=target_complaint, user=target_worker)
            
            # Create notification for worker when assigned a ticket
            if target_worker and target_complaint:
                try:
                    title = "Призначено скаргу"
                    message = f"Адміністратор призначив вам скаргу: '{target_complaint.title}'"
                    Notification.objects.create(
                        user=target_worker,
                        title=title,
                        message=message,
                        complaint=target_complaint
                    )
                except Exception as e:
                    print("Error creating worker notification on ticket post:", e)
            
            # Create notification for student when worker is assigned
            if target_complaint and target_complaint.user and target_worker:
                try:
                    student_title = "Призначено майстра 🛠️"
                    student_message = f"До вашої заявки '{target_complaint.title}' призначено майстра {target_worker.first_name} {target_worker.last_name}. Очікуйте на виконання роботи."
                    Notification.objects.create(
                        user=target_complaint.user,
                        title=student_title,
                        message=student_message,
                        complaint=target_complaint
                    )
                except Exception as e:
                    print("Failed to notify student of worker assignment on ticket post:", e)
                    
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TicketDetailView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    def get(self, request, ticket_id):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
            
        is_admin = user_profile.role and user_profile.role.role_name.lower() in ['admin', 'адміністратор']
        is_worker = user_profile.role and user_profile.role.role_name.lower() == 'worker'
        
        if not is_admin and not is_worker:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            ticket = Ticket.objects.get(ticket_id=ticket_id)
        except Ticket.DoesNotExist:
            return Response({'error': 'Ticket not found'}, status=status.HTTP_404_NOT_FOUND)
            
        if is_worker and ticket.user != user_profile:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            
        serializer = TicketSerializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, ticket_id):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile or not user_profile.role or user_profile.role.role_name.lower() not in ['admin', 'адміністратор']:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            ticket = Ticket.objects.get(ticket_id=ticket_id)
        except Ticket.DoesNotExist:
            return Response({'error': 'Ticket not found'}, status=status.HTTP_404_NOT_FOUND)
        
        old_worker = ticket.user
        old_deadline = ticket.deadline
        
        worker_id = request.data.get('user')
        worker_changed = False
        if worker_id is not None:
            if worker_id == "":
                ticket.user = None
                worker_changed = old_worker is not None
            else:
                try:
                    target_worker = UserProfile.objects.get(user_id=worker_id)
                    if not target_worker.role or target_worker.role.role_name.lower() != 'worker':
                        return Response({'error': 'User is not a worker'}, status=status.HTTP_400_BAD_REQUEST)
                    ticket.user = target_worker
                    worker_changed = old_worker != target_worker
                except UserProfile.DoesNotExist:
                    return Response({'error': 'Worker not found'}, status=status.HTTP_404_NOT_FOUND)
        
        deadline = request.data.get('deadline')
        deadline_changed = False
        if deadline is not None:
            if deadline == "":
                ticket.deadline = None
                deadline_changed = old_deadline is not None
            else:
                ticket.deadline = deadline
            
        ticket.save()
        ticket.refresh_from_db()
        
        # After save, check if deadline changed
        if old_deadline != ticket.deadline:
            deadline_changed = True
            
        # Send notifications
        # 1. Assignment notification to NEW worker
        if worker_changed and ticket.user:
            try:
                title = "Призначено скаргу"
                message = f"Адміністратор призначив вам скаргу: '{ticket.complaint.title}'"
                Notification.objects.create(
                    user=ticket.user,
                    title=title,
                    message=message,
                    complaint=ticket.complaint
                )
            except Exception as e:
                print("Error creating worker notification in patch:", e)
            
            # Send notification to the student about worker assignment
            if ticket.complaint and ticket.complaint.user:
                try:
                    student_title = "Призначено майстра 🛠️"
                    student_message = f"До вашої заявки '{ticket.complaint.title}' призначено майстра {ticket.user.first_name} {ticket.user.last_name}. Очікуйте на виконання роботи."
                    Notification.objects.create(
                        user=ticket.complaint.user,
                        title=student_title,
                        message=student_message,
                        complaint=ticket.complaint
                    )
                except Exception as se:
                    print("Failed to notify student of worker assignment on ticket patch:", se)
                
        # 2. Deadline change notification to CURRENT worker
        if deadline_changed and ticket.user and not worker_changed:
            try:
                def format_dt(dt):
                    if not dt:
                        return "не вказано"
                    try:
                        import zoneinfo
                        kyiv_tz = zoneinfo.ZoneInfo("Europe/Kyiv")
                        local_dt = dt.astimezone(kyiv_tz)
                        return local_dt.strftime("%d.%m.%Y %H:%M")
                    except Exception:
                        return str(dt)
                
                old_deadline_str = format_dt(old_deadline)
                new_deadline_str = format_dt(ticket.deadline)
                
                title = "Зміна дедлайну"
                message = f"Адміністратор змінив дедлайн призначеної скарги з '{old_deadline_str}' на '{new_deadline_str}'"
                Notification.objects.create(
                    user=ticket.user,
                    title=title,
                    message=message,
                    complaint=ticket.complaint
                )
            except Exception as e:
                print("Error creating deadline change notification:", e)
                
        serializer = TicketSerializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)

class EmployeeListView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile or not user_profile.role or user_profile.role.role_name.lower() not in ['admin', 'адміністратор']:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            
        # Return all users who could be assigned as workers
        employees = UserProfile.objects.filter(role__role_name__iexact='worker')
        serializer = UserSerializer(employees, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_profile = getattr(request.user, 'profile', None)
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        notifications = Notification.objects.filter(user=user_profile).order_by('-created_at')[:50]
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, notification_id):
        user_profile = getattr(request.user, 'profile', None)
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            notification = Notification.objects.get(notification_id=notification_id, user=user_profile)
        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)
        
        notification.is_read = True
        notification.save()
        serializer = NotificationSerializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_profile = getattr(request.user, 'profile', None)
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        Notification.objects.filter(user=user_profile, is_read=False).update(is_read=True)
        return Response({'status': 'all notifications marked as read'}, status=status.HTTP_200_OK)


class ChangeUserRoomView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        
        building_id = request.data.get('building_number')
        room_number = request.data.get('room_number')
        
        if not building_id or not room_number:
            return Response({'error': 'building_number and room_number are required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            building = DormitoryBuilding.objects.get(building_id=building_id)
        except DormitoryBuilding.DoesNotExist:
            return Response({'error': 'Building not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        place, _ = Place.objects.get_or_create(
            building=building,
            place_name=room_number
        )
        
        user_profile.place = place
        user_profile.save()
        
        return Response({'detail': 'Room updated successfully'}, status=status.HTTP_200_OK)


class CampusStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import CampusStatus
        from .serializers import CampusStatusSerializer
        status_obj = CampusStatus.objects.first()
        if not status_obj:
            status_obj = CampusStatus.objects.create()
        serializer = CampusStatusSerializer(status_obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        from .models import CampusStatus, Announcement
        from .serializers import CampusStatusSerializer
        user_profile = UserProfile.objects.filter(user=request.user).first()
        if not user_profile or not user_profile.role or user_profile.role.role_name.lower() not in ['admin', 'адміністратор']:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        status_obj = CampusStatus.objects.first()
        if not status_obj:
            status_obj = CampusStatus.objects.create()
        
        serializer = CampusStatusSerializer(status_obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            
            # If announcement text is provided, persist it to announcement history
            announcement_title = request.data.get('announcement_title')
            announcement_text = request.data.get('announcement_text')
            if announcement_title and announcement_text:
                Announcement.objects.create(
                    title=announcement_title.strip(),
                    text=announcement_text.strip()
                )
                
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AnnouncementListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import Announcement
        from .serializers import AnnouncementSerializer
        announcements = Announcement.objects.all().order_by('-created_at')
        serializer = AnnouncementSerializer(announcements, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminResidentsListView(APIView):
    def get_permissions(self):
        from .permissions import IsCustomAdmin
        return [IsCustomAdmin()]

    def get(self, request):
        from .models import UserProfile
        from .serializers import UserSerializer
        
        building_id = request.query_params.get('building_id')
        queryset = UserProfile.objects.filter(role__role_name='student').select_related('place__building', 'role')
        
        if building_id:
            if building_id == 'unassigned':
                queryset = queryset.filter(place__isnull=True)
            else:
                queryset = queryset.filter(place__building_id=building_id)
                
        serializer = UserSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminRelocateResidentView(APIView):
    def get_permissions(self):
        from .permissions import IsCustomAdmin
        return [IsCustomAdmin()]

    def post(self, request):
        from .models import UserProfile, DormitoryBuilding, Place
        from .serializers import UserSerializer
        
        profile_user_id = request.data.get('user_id')
        building_id = request.data.get('building_id')
        room_name = request.data.get('room_name', '').strip()
        
        if not profile_user_id or not building_id or not room_name:
            return Response({'error': 'user_id, building_id, and room_name are required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            profile = UserProfile.objects.get(user_id=profile_user_id)
        except UserProfile.DoesNotExist:
            return Response({'error': 'Resident profile not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        try:
            building = DormitoryBuilding.objects.get(building_id=building_id)
        except DormitoryBuilding.DoesNotExist:
            return Response({'error': 'Building not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        place, _ = Place.objects.get_or_create(
            building=building,
            place_name=room_name
        )
        
        profile.place = place
        profile.save()
        
        # Create student notification for relocation
        try:
            Notification.objects.create(
                user=profile,
                title="Вас переселено 🏠",
                message=f"Адміністратор оновив ваші дані проживання. Нова адреса: {building.name}, кімната {place.place_name}.",
                complaint=None
            )
        except Exception as ne:
            print("Error creating relocation notification:", ne)
            
        return Response(UserSerializer(profile).data, status=status.HTTP_200_OK)

