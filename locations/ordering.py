from rest_framework.filters import OrderingFilter


class StableOrderingFilter(OrderingFilter):
    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        if ordering and not any(field.lstrip("-") == "id" for field in ordering):
            return (*ordering, "-id")
        return ordering
