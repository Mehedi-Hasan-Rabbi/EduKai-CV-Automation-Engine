from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """
    Standard pagination used across all list endpoints.

    Query params:
        ?page=1         current page (default: 1)
        ?page_size=20   items per page (default: 20, max: 100)
    """
    page_size                = 20
    page_size_query_param    = "page_size"
    max_page_size            = 100
    page_query_param         = "page"

    def get_paginated_response(self, data):
        return Response({
            "pagination": {
                "total":       self.page.paginator.count,
                "page":        self.page.number,
                "page_size":   self.get_page_size(self.request),
                "total_pages": self.page.paginator.num_pages,
                "has_next":    self.page.has_next(),
                "has_previous": self.page.has_previous(),
                "next":        self.get_next_link(),
                "previous":    self.get_previous_link(),
            },
            "results": data,
        })