"""
Supabase connection — një file, një rol.
Gjithçka që ka lidhje me databazën shkon këtu.
"""
from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()

# ── Inicializo Supabase Client ─────────────────────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ SUPABASE_URL dhe SUPABASE_KEY duhet të jenë në .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_db() -> Client:
    """
    Kthen Supabase client-in.
    Përdoret nga të gjitha file-t e tjera.
    
    Usage:
        from database import get_db
        db = get_db()
        db.table("metrics").select("*").execute()
    """
    return supabase
