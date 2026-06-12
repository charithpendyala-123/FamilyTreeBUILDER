import base64
import os
from streamlit_agraph import Node, Edge, Config

# Base64 Silhouette SVGs for fallback profile images
MALE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
<circle cx="50" cy="50" r="50" fill="#e2edf0"/>
<circle cx="50" cy="35" r="18" fill="#23787c"/>
<path d="M50,56 C30,56 20,70 20,85 L80,85 C80,70 70,56 50,56 Z" fill="#23787c"/>
</svg>"""

FEMALE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
<circle cx="50" cy="50" r="50" fill="#fceef0"/>
<circle cx="50" cy="35" r="18" fill="#c05c6e"/>
<path d="M50,56 C32,56 22,70 22,85 L78,85 C78,70 68,56 50,56 Z" fill="#c05c6e"/>
<path d="M50,20 C42,20 38,28 38,36 C38,40 40,44 42,46 C44,48 45,52 46,55 L54,55 C55,52 56,48 58,46 C60,44 62,40 62,36 C62,28 58,20 50,20 Z" fill="#c05c6e"/>
</svg>"""

UNKNOWN_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
<circle cx="50" cy="50" r="50" fill="#f0f2f5"/>
<circle cx="50" cy="35" r="18" fill="#5f6368"/>
<path d="M50,56 C30,56 20,70 20,85 L80,85 C80,70 70,56 50,56 Z" fill="#5f6368"/>
</svg>"""

def get_base64_svg(svg_str: str) -> str:
    """Encodes an SVG string to a Base64 data URL."""
    encoded = base64.b64encode(svg_str.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{encoded}"

def get_base64_image(image_path: str) -> str:
    """Encodes a local image to a Base64 data URL."""
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode("utf-8")
                ext = os.path.splitext(image_path)[1].lower().replace(".", "")
                if ext == "jpg":
                    ext = "jpeg"
                return f"data:image/{ext};base64,{encoded}"
        except Exception:
            pass
    return None

def build_graph(persons: list, relationships: list, selected_person_id: int = None):
    """Transforms database persons and relationships into streamlit-agraph Nodes and Edges."""
    nodes = []
    edges = []
    
    for person in persons:
        pid = person["id"]
        gender = person["gender"]
        
        image_uri = None
        if person.get("photo_path"):
            image_uri = get_base64_image(person["photo_path"])
        
        if not image_uri:
            if gender == "Male":
                image_uri = get_base64_svg(MALE_SVG)
            elif gender == "Female":
                image_uri = get_base64_svg(FEMALE_SVG)
            else:
                image_uri = get_base64_svg(UNKNOWN_SVG)

        border_color = "#23787c" if gender == "Male" else ("#c05c6e" if gender == "Female" else "#5f6368")
        background_color = "#ffffff"
        
        if selected_person_id and pid == selected_person_id:
            border_color = "#ffaa00"
            background_color = "#fffbeb"
            
        color_config = {
            "border": border_color,
            "background": background_color,
            "highlight": {
                "border": "#ffaa00",
                "background": "#fffbeb"
            }
        }

        name_str = f"{person['first_name']} {person['surname_now'] or ''}".strip()
        dob_str = person.get("birth_date") or "Unknown"
        display_label = f"{name_str}\n({dob_str})"

        if person.get("deceased") == 1:
            display_label += "\n[Deceased]"

        nodes.append(
            Node(
                id=str(pid),
                label=display_label,
                size=45,
                shape="circularImage",
                image=image_uri,
                color=color_config,
                borderWidth=4,
                font={"size": 12, "color": "#333333", "face": "Arial", "multi": True}
            )
        )

    for rel in relationships:
        p1 = str(rel["person1_id"])
        p2 = str(rel["person2_id"])
        rel_type = rel["relationship_type"]
        
        if rel_type == "parent-child":
            edges.append(
                Edge(
                    source=p1,
                    target=p2,
                    label="",
                    color="#23787c",
                    width=2,
                    arrows={"to": {"enabled": True, "scaleFactor": 0.8}}
                )
            )
        elif rel_type == "partner":
            edges.append(
                Edge(
                    source=p1,
                    target=p2,
                    label="Partner",
                    color="#c05c6e",
                    width=2,
                    dashes=True,
                    arrows={"to": {"enabled": False}, "from": {"enabled": False}}
                )
            )
        elif rel_type == "sibling":
            edges.append(
                Edge(
                    source=p1,
                    target=p2,
                    label="Sibling",
                    color="#7f8c8d",
                    width=2,
                    dashes=True,
                    arrows={"to": {"enabled": False}, "from": {"enabled": False}}
                )
            )

    return nodes, edges

def get_graph_config(height: int = 550):
    """Returns the config object for streamlit-agraph with hierarchical layout settings."""
    return Config(
        width=750,
        height=height,
        directed=True,
        physics=False,
        hierarchical={
            "enabled": True,
            "levelSeparation": 120,
            "nodeSpacing": 180,
            "treeSpacing": 200,
            "blockShifting": True,
            "edgeMinimization": True,
            "parentCentralization": True,
            "direction": "UD",
            "sortMethod": "directed"
        }
    )