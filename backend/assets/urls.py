from django.urls import path
from . import report_views, views

urlpatterns = [
    # Auth
    path('auth/login/', views.login),
    path('auth/logout/', views.logout),
    path('auth/me/', views.me),

    # Today
    path('today/', views.today),

    # Work orders
    path('work-orders/<uuid:pk>/', views.work_order_detail),
    path('work-orders/<uuid:pk>/start/', views.work_order_start),
    path('work-orders/<uuid:pk>/end/', views.work_order_end),

    # Alarms
    path('alarms/', views.alarms),
    path('alarms/<uuid:pk>/', views.alarm_detail),
    path('alarms/<uuid:pk>/resolve/', views.alarm_resolve),
    path('alarms/<uuid:pk>/notes/', views.alarm_add_note),

    # Base stations & assets (pickers)
    path('base-stations/', views.base_stations),
    path('assets/', views.assets),

    # Inspection responses
    path('inspection-responses/', views.inspection_responses),
    path('inspection-responses/<uuid:pk>/', views.inspection_response_detail),

    # Checklist responses
    path('checklist-responses/<uuid:pk>/', views.checklist_response_detail),

    # Issues
    path('issues/', views.issues),
    path('issues/<uuid:pk>/', views.issue_detail),

    # Conditions
    path('conditions/', views.conditions),

    # Meter readings
    path('meter-readings/', views.meter_readings),

    # Vendors & parts
    path('vendors/', views.vendors),
    path('parts/', views.parts),

    # Diesel deliveries
    path('diesel-deliveries/', views.diesel_deliveries),

    # Part requests
    path('part-requests/', views.part_requests),
    path('part-requests/<uuid:pk>/cancel/', views.part_request_cancel),
    path('part-request-lines/<uuid:pk>/receipts/', views.part_request_line_receipts),
    path('part-deliveries/<uuid:pk>/confirm-received/', views.part_delivery_confirm_received),

    # Part usage
    path('part-usages/', views.part_usages),
    path('team-stock/', views.team_stock),

    # Cluster Manager lists (scoped to the manager's cluster)
    path('manager/part-requests/', views.manager_part_requests),
    path('manager/part-usages/', views.manager_part_usages),
    path('manager/stock/', views.manager_stock),
    path('manager/requests-summary/', views.manager_requests_summary),
    path('manager/usage-summary/', views.manager_usage_summary),

    # Maintenance reports (Cluster Manager)
    path('reports/overview/', report_views.overview),
    path('reports/stations/<uuid:pk>/', report_views.station_detail),
    path('reports/assets/<uuid:pk>/', report_views.asset_detail),
    path('reports/asset-types/', report_views.asset_types),
    path('reports/asset-types/<uuid:pk>/grid/', report_views.asset_type_grid),
    path('reports/staff/', report_views.staff),

    # Notifications
    path('notifications/', views.notifications),
    path('notifications/<uuid:pk>/read/', views.notification_read),

    # Safety reports
    path('safety-reports/', views.safety_reports),

    # Attachments
    path('attachments/', views.attachments),

    # Asset categories & checkpoints (admin)
    path('asset-categories/', views.asset_categories),
    path('asset-categories/<uuid:pk>/', views.asset_category_detail),
    path('checklist-questions/', views.checklist_questions),
    path('checklist-questions/<uuid:pk>/', views.checklist_question_detail),
]
