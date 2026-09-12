# Copyright 2023 Canonical
# See LICENSE file for licensing details.
"""This file defines the schemas for the provider and requirer sides of the kubeflow-dashboard-links interface.

Examples:
    Requirer:
        unit: <empty>
        app: {
            "dashboard_links": '[
                {
                    "text": "Some link text",
                    "link": "/some-relative-link",
                    "location": "menu",
                    "type": "item",
                    "icon": "assessment",
                    "desc": "link description"
                }
            ]'
        }
"""

from pydantic import BaseModel


class DashboardItem(BaseModel):
    """Representation of a Kubeflow Dashboard link entry.

    See https://www.kubeflow.org/docs/components/central-dash/customizing-menu/ for more details.

    Args:
        text: The text shown for the link
        link: The link (a relative link for `location=menu` or `location=quick`, eg: `/mlflow`,
              or a full URL for other locations, eg: http://my-website.com)
        type: A type of link entry (typically, "item")
        icon: An icon for the link, from
              https://kevingleason.me/Polymer-Todo/bower_components/iron-icons/demo/index.html
        location: Link's location on the dashboard.  One of `menu`, `external`, `quick`,
                  and `documentation`.
    """

    text: str
    link: str
    location: str
    icon: str = "icons:link"
    type: str = "item"
    desc: str = ""


class RequirerAppData(BaseModel):
    """The requirer's application databag."""

    dashboard_links: list[DashboardItem]


ProviderAppData = None
ProviderUnitData = None
RequirerUnitData = None
