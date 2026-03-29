from django.urls import path
from candidate.views import (
    BatchListView,
    BatchStatusView,
    BatchDeleteView,
    BulkCVUploadView,
    CandidateDetailView,
    CandidateDeleteView,
    CandidateListView,
    CandidateNearbyContactsView,
    CandidateUpdateView,
    CandidateRewriteView,
    CandidateRewriteStatusView,
    CandidateNearbyOrganizationsView,
    CandidateNearbyContactsView,
    SendToContactsView,
    SendToContactsStatusView,
)

app_name = "candidate"

urlpatterns = [
    path("",                                    CandidateListView.as_view(),   name="candidate_list"),
    path("upload/",                             BulkCVUploadView.as_view(),    name="bulk_upload"),
    
    path("send-status/<str:task_id>/", SendToContactsStatusView.as_view(), name="send_to_contacts_status"),
    
    path("<uuid:candidate_id>/",                CandidateDetailView.as_view(), name="candidate_detail"),
    path("<uuid:candidate_id>/update/",         CandidateUpdateView.as_view(), name="candidate_update"),
    path("<uuid:candidate_id>/delete/",         CandidateDeleteView.as_view(), name="candidate_delete"),
    path("<uuid:candidate_id>/nearby-organizations/", CandidateNearbyOrganizationsView.as_view(), name="candidate_nearby_organizations"),
    path("<uuid:candidate_id>/nearby-contacts/", CandidateNearbyContactsView.as_view(), name="candidate_nearby_contacts"),

    path("<uuid:candidate_id>/rewrite/",         CandidateRewriteView.as_view(),       name="candidate_rewrite"),
    path("<uuid:candidate_id>/rewrite/status/",  CandidateRewriteStatusView.as_view(), name="candidate_rewrite_status"),
    path("<uuid:candidate_id>/send-to-contacts/", SendToContactsView.as_view(), name="send_to_contacts"),

    path("batches/",                            BatchListView.as_view(),        name="batch_list"),
    path("batches/<uuid:batch_id>/",            BatchStatusView.as_view(),     name="batch_status"),
    path("batches/<uuid:batch_id>/delete/",     BatchDeleteView.as_view(),     name="batch_delete"),
]