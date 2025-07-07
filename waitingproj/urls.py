# waitingproj/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Include the URLs from your 'waitingroom' app
    # This means any URLs defined in waitingroom/urls.py will be prefixed with nothing here,
    # so they will be directly accessible (e.g., /join-queue/, /doctor/1/).
    path('', include('waitingroom.urls')),
]
