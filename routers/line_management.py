import sqlite3
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.database import get_db_connection
from utils.parameters import obis_to_column 
templates = Jinja2Templates(directory="templates")

router = APIRouter() 
@router.get("/line-management",response_class=HTMLResponse) 
async def line_management(request: Request, message: str=None): 
    conn = get_db_connection()   
    lines = conn.execute("SELECT *FROM lines").fetchall()  
    print(lines)     
    conn.close()
    return templates.TemplateResponse("line_management.html", {"request": request, "lines":lines,"message":message})
@router.post("/add-line") 
async def add_line( 
    line_name: str = Form(...),
    line_level: str = Form(...),  
    parent_node: str = Form(None),  
):  
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO lines 
            (line_name, line_level, parent_node)
            VALUES (?, ?, ?) 
        """, (line_name, line_level, parent_node,))  
        conn.commit()
        message = "✅ Line added successfully."
    except sqlite3.IntegrityError:
        message = "⚠️ Same Line is already registered." 
    finally:
        conn.close()

    return RedirectResponse(url=f"/line-management?message={message}", status_code=303)   

@router.post("/edit-line")
async def edit_line(
    original_line_name: str = Form(...),  # hidden input for original name
    line_name: str = Form(...),
    line_level: str = Form(...),
    parent_node: str = Form(None),
):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Rule 1: Parent node cannot be itself
        if parent_node == original_line_name:
            message = "❌ Parent node cannot be the same as the line itself."
            return RedirectResponse(url=f"/line-management?message={message}", status_code=303)

        # Rule 2: Parent node cannot be any of its descendants
        descendants = get_descendants(cursor, original_line_name)
        if parent_node in descendants:
            message = "❌ Parent node cannot be a child or descendant of this line."
            return RedirectResponse(url=f"/line-management?message={message}", status_code=303)

        # If all checks pass, update the line
        cursor.execute("""
            UPDATE lines
            SET line_name = ?, line_level = ?, parent_node = ?
            WHERE line_name = ?
        """, (line_name, line_level, parent_node, original_line_name))
        conn.commit()

        message = "✅ Line updated successfully."
    except sqlite3.IntegrityError:
        message = "⚠️ A line with the same name already exists."
    finally:
        conn.close()

    return RedirectResponse(url=f"/line-management?message={message}", status_code=303)

@router.post("/delete-line")  
async def delete_line( line_name : str = Form(...)):   
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM lines WHERE line_name = ?", (line_name,)) 
    conn.commit()
    conn.close()
    message = f"✅ Line is successfully deleted."  
    return RedirectResponse(url=f"/line-management?message={message}", status_code=303) 


def get_lines_from_db():
    conn = get_db_connection()  
    cursor = conn.cursor()
    cursor.execute("SELECT line_name, parent_node FROM lines")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def build_tree(data):
    lookup = {}

    # Create lookup nodes
    for d in data:
        lookup[d["line_name"]] = {"text": d["line_name"], "children": []}

    # Assign children to parents
    root_nodes = []
    for d in data:
        if d["parent_node"] is None or d["parent_node"] == '':
            root_nodes.append(lookup[d["line_name"]])
        else:
            lookup[d["parent_node"]]["children"].append(lookup[d["line_name"]])

    return root_nodes  # jsTree expects a list

@router.get("/line-tree-data")
def get_line_tree():
    lines = get_lines_from_db()
    tree_result = build_tree(lines)
    return JSONResponse(tree_result)  




def get_descendants(cursor, line_name):
    """
    Recursively get all descendant lines for a given line_name.
    """
    descendants = set()
    stack = [line_name]

    while stack:
        current = stack.pop()
        cursor.execute("SELECT line_name FROM lines WHERE parent_node = ?", (current,))
        children = [row[0] for row in cursor.fetchall()]
        for child in children:
            if child not in descendants:
                descendants.add(child)
                stack.append(child)

    return descendants 