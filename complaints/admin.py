from django.contrib import admin
from .models import Complaint, UserProfile, Comment, DormitoryBuilding, ComplaintCategory, Role, Ticket, Place
# Register your models here.
admin.site.register(Complaint)
admin.site.register(UserProfile)
admin.site.register(Role)
admin.site.register(DormitoryBuilding)
admin.site.register(ComplaintCategory)
admin.site.register(Comment)
admin.site.register(Ticket)
admin.site.register(Place)