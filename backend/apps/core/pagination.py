"""Custom pagination defaults for the REST API.

Phase 1 preview fetches all 22K stops client-side; letting the client
request up to 10 000 per page drops that from 225 requests to 3.
"""
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 10000
