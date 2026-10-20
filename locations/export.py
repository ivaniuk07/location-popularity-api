from io import BytesIO

import pandas as pd
from django.http import HttpResponse, JsonResponse


EXPORT_COLUMNS = (
    "id",
    "name",
    "description",
    "category_id",
    "category_name",
    "address",
    "latitude",
    "longitude",
    "author_id",
    "author_username",
    "created_at",
    "rating",
    "review_count",
    "views_last_7_days",
    "popularity",
)


def export_locations(queryset, file_format):
    rows = [
        {
            "id": location.pk,
            "name": location.name,
            "description": location.description,
            "category_id": location.category_id,
            "category_name": location.category.name,
            "address": location.address,
            "latitude": str(location.latitude),
            "longitude": str(location.longitude),
            "author_id": location.author_id,
            "author_username": (
                location.author.get_username() if location.author else None
            ),
            "created_at": location.created_at.isoformat(),
            "rating": location.rating,
            "review_count": location.review_count,
            "views_last_7_days": location.views_last_7_days,
            "popularity": location.popularity,
        }
        for location in queryset.iterator(chunk_size=500)
    ]

    if file_format == "json":
        response = JsonResponse(rows, safe=False, json_dumps_params={"ensure_ascii": False})
    else:
        output = BytesIO()
        pd.DataFrame.from_records(rows, columns=EXPORT_COLUMNS).to_csv(
            output, index=False, encoding="utf-8-sig", lineterminator="\n"
        )
        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")

    response["Content-Disposition"] = f'attachment; filename="locations.{file_format}"'
    return response
