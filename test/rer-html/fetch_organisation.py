"""Fetch and save HTML from GET /Organisations/{organisationId}.

Gets the first organisation ID from the user dashboard automatically.
"""

import os

from _auth import get_client
from selectolax.lexbor import LexborHTMLParser as HTMLParser

OUTPUT = os.path.join(os.path.dirname(__file__), "organisation.html")

client = get_client()

# First get org ID from the dashboard
dashboard = client.session.get(client.base_url + "User")
dashboard.raise_for_status()
tree = HTMLParser(dashboard.text)

# Organisation links look like /Organisations/GEN0000000
org_links = []
for node in tree.css("a"):
    href = node.attrs.get("href")
    if href and "/Organisations/GEN" in href:
        org_links.append(node)
if not org_links:
    print("No organisation links found on dashboard. Check the HTML structure.")
    raise SystemExit(1)

# Extract org ID from the first link
org_href = org_links[0].attrs.get("href")
if not org_href:
    print("First organisation link is missing an href.")
    raise SystemExit(1)
org_id = org_href.split("/Organisations/")[-1].split("/")[0]
print(f"Using organisation ID: {org_id}")

response = client.session.get(client.base_url + f"Organisations/{org_id}")
response.raise_for_status()

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(response.text)

print(f"Saved HTML to {OUTPUT}")
print(f"Status: {response.status_code}")
