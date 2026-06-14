from pathlib import Path
from datetime import datetime
from urllib.parse import quote
import sqlite3

import pandas as pd
import qrcode
import streamlit as st
from fpdf import FPDF

try:
    from supabase import create_client
except Exception:
    create_client = None


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
QR_DIR = BASE_DIR / "storage" / "qr"
PDF_DIR = BASE_DIR / "storage" / "pdf"
PHOTO_DIR = BASE_DIR / "storage" / "photos"
EXPORTS_DIR = BASE_DIR / "exports"
DB_PATH = DATA_DIR / "petpass.db"
SUPABASE_PHOTO_BUCKET = "pet-photos"
DEMO_CLINIC_NAME = "Clinica Demo PetPass MX"
DEMO_CLINIC_CODE = "PETPASS-DEMO"


def supabase_credentials():
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
    except Exception:
        url = ""
        key = ""
    return str(url or "").strip(), str(key or "").strip()


def supabase_enabled():
    url, key = supabase_credentials()
    return bool(create_client and url and key)


@st.cache_resource
def get_supabase_client(url, key):
    return create_client(url, key)


def sb():
    url, key = supabase_credentials()
    client = create_client(url, key)
    access_token = st.session_state.get("access_token")
    refresh_token = st.session_state.get("refresh_token")
    if access_token and refresh_token:
        try:
            client.auth.set_session(access_token, refresh_token)
        except Exception:
            pass
    return client


def cloud_mode():
    return supabase_enabled() and bool(st.session_state.get("clinica_id"))


def current_clinic_id():
    return st.session_state.get("clinica_id")


def rows_to_df(rows):
    return pd.DataFrame(rows or [])


def obj_value(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def set_auth_state(auth_response):
    user = obj_value(auth_response, "user")
    session = obj_value(auth_response, "session")
    access_token = obj_value(session, "access_token")
    refresh_token = obj_value(session, "refresh_token")
    user_id = obj_value(user, "id")

    st.session_state["auth_user"] = {
        "id": user_id,
        "email": obj_value(user, "email", ""),
    }
    st.session_state["access_token"] = access_token
    st.session_state["refresh_token"] = refresh_token
    st.session_state["is_authenticated"] = bool(access_token)
    st.session_state["modo_demo"] = False
    return user_id


def clear_session_state():
    for key in [
        "auth_user",
        "access_token",
        "refresh_token",
        "clinica_id",
        "clinica_nombre",
        "modo_demo",
        "is_authenticated",
    ]:
        st.session_state.pop(key, None)


def load_user_clinic(user_id):
    membership = (
        sb()
        .table("clinica_usuarios")
        .select("*")
        .eq("user_id", user_id)
        .eq("activo", True)
        .limit(1)
        .execute()
    )
    if not membership.data:
        return None

    clinic_id = membership.data[0]["clinica_id"]
    clinic = (
        sb()
        .table("clinicas")
        .select("*")
        .eq("id", clinic_id)
        .limit(1)
        .execute()
    )
    return clinic.data[0] if clinic.data else None


def ensure_demo_clinic():
    client = sb()
    found = (
        client.table("clinicas")
        .select("*")
        .eq("codigo_acceso", DEMO_CLINIC_CODE)
        .limit(1)
        .execute()
    )
    if found.data:
        return found.data[0]

    created = (
        client.table("clinicas")
        .insert(
            {
                "nombre": DEMO_CLINIC_NAME,
                "telefono": "5512345678",
                "email": "demo@petpass.mx",
                "codigo_acceso": DEMO_CLINIC_CODE,
                "activo": True,
                "plan": "demo",
            }
        )
        .execute()
    )
    return created.data[0] if created.data else None


def show_clinic_gate():
    page_header(
        "PetPass MX V3",
        "Acceso seguro",
        "Inicia sesión, registra tu clínica o usa la demo pública con datos ficticios.",
    )
    login_tab, signup_tab, demo_tab = st.tabs(
        ["Iniciar sesión", "Crear cuenta / registrar clínica", "Usar demo pública"]
    )

    with login_tab:
        with st.form("login_supabase"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Iniciar sesión")

        if submitted:
            try:
                response = sb().auth.sign_in_with_password(
                    {"email": email.strip(), "password": password}
                )
                user_id = set_auth_state(response)
                clinic = load_user_clinic(user_id)
                if clinic:
                    st.session_state["clinica_id"] = clinic["id"]
                    st.session_state["clinica_nombre"] = clinic["nombre"]
                    st.session_state["modo_demo"] = False
                    st.success("Sesión iniciada.")
                    st.rerun()
                else:
                    clear_session_state()
                    st.error("Tu usuario no tiene clínica asignada.")
            except Exception as exc:
                st.error(f"No se pudo iniciar sesión: {exc}")

    with signup_tab:
        with st.form("signup_supabase"):
            nombre_clinica = st.text_input("Nombre de clínica")
            responsable = st.text_input("Nombre responsable")
            email = st.text_input("Email de acceso")
            password = st.text_input("Password", type="password")
            telefono = st.text_input("Teléfono opcional")
            submitted = st.form_submit_button("Crear cuenta y clínica")

        if submitted:
            if not nombre_clinica.strip() or not email.strip() or not password:
                st.error("Clínica, email y password son obligatorios.")
                return
            try:
                response = sb().auth.sign_up(
                    {"email": email.strip(), "password": password}
                )
                user_id = set_auth_state(response)
                if not st.session_state.get("is_authenticated"):
                    st.info("Cuenta creada. Confirma tu email o desactiva confirmación para demo, luego inicia sesión.")
                    return

                codigo = (
                    safe_file_part(nombre_clinica).upper()[:18]
                    + "-"
                    + datetime.now().strftime("%H%M%S")
                )
                created = (
                    sb()
                    .table("clinicas")
                    .insert(
                        {
                            "nombre": nombre_clinica.strip(),
                            "telefono": telefono.strip(),
                            "email": email.strip(),
                            "codigo_acceso": codigo,
                            "activo": True,
                            "owner_user_id": user_id,
                            "creado_por": user_id,
                            "plan": "real",
                        }
                    )
                    .execute()
                )
                clinic = created.data[0]
                sb().table("clinica_usuarios").insert(
                    {
                        "clinica_id": clinic["id"],
                        "user_id": user_id,
                        "rol": "admin",
                        "activo": True,
                    }
                ).execute()
                st.session_state["clinica_id"] = clinic["id"]
                st.session_state["clinica_nombre"] = clinic["nombre"]
                st.session_state["modo_demo"] = False
                st.success("Cuenta y clínica creadas.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo crear la cuenta: {exc}")

    with demo_tab:
        st.warning("Demo pública con datos ficticios. No ingresar datos reales.")
        if st.button("Usar demo pública"):
            try:
                clear_session_state()
                clinic = ensure_demo_clinic()
                if clinic:
                    st.session_state["clinica_id"] = clinic["id"]
                    st.session_state["clinica_nombre"] = clinic["nombre"]
                    st.session_state["modo_demo"] = True
                    st.session_state["is_authenticated"] = False
                    st.rerun()
                else:
                    st.error("No se pudo crear o abrir la demo pública.")
            except Exception as exc:
                st.error(f"No se pudo abrir la demo pública: {exc}")


def ensure_dirs():
    for folder in [DATA_DIR, QR_DIR, PDF_DIR, PHOTO_DIR, EXPORTS_DIR]:
        folder.mkdir(parents=True, exist_ok=True)


def get_conn():
    ensure_dirs()
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tutores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                email TEXT,
                notas TEXT,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mascotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tutor_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                especie TEXT,
                raza TEXT,
                sexo TEXT,
                fecha_nacimiento TEXT,
                peso REAL,
                foto_path TEXT,
                notas TEXT,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tutor_id) REFERENCES tutores(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vacunas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mascota_id INTEGER NOT NULL,
                nombre_vacuna TEXT NOT NULL,
                fecha_aplicada TEXT,
                proxima_fecha TEXT,
                responsable TEXT,
                notas TEXT,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (mascota_id) REFERENCES mascotas(id)
            )
            """
        )
        columnas = [row[1] for row in conn.execute("PRAGMA table_info(mascotas)").fetchall()]
        if "foto_path" not in columnas:
            conn.execute("ALTER TABLE mascotas ADD COLUMN foto_path TEXT")


def read_df(query, params=()):
    with get_conn() as conn:
        return pd.read_sql_query(query, conn, params=params)


def execute(query, params=()):
    with get_conn() as conn:
        conn.execute(query, params)
        conn.commit()


def get_counts():
    if cloud_mode():
        tutores = len(load_tutores())
        mascotas = len(load_mascotas())
        vacunas = len(load_vacunas())
        return tutores, mascotas, vacunas

    with get_conn() as conn:
        tutores = conn.execute("SELECT COUNT(*) FROM tutores").fetchone()[0]
        mascotas = conn.execute("SELECT COUNT(*) FROM mascotas").fetchone()[0]
        vacunas = conn.execute("SELECT COUNT(*) FROM vacunas").fetchone()[0]
    return tutores, mascotas, vacunas


def apply_visual_style():
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(180deg, #f3fbf8 0%, #ffffff 42%);
            color: #173b3f;
        }
        .block-container {
            max-width: 1180px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        h1, h2, h3 {
            color: #143f42;
            letter-spacing: 0;
        }
        [data-testid="stSidebar"] {
            background: #123f42;
        }
        [data-testid="stSidebar"] * {
            color: #f4fffb;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label {
            border-radius: 10px;
            padding: 0.35rem 0.6rem;
            margin-bottom: 0.15rem;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #d8eee6;
            border-left: 6px solid #24a484;
            border-radius: 14px;
            padding: 1rem 1rem 0.8rem;
            box-shadow: 0 8px 24px rgba(18, 63, 66, 0.08);
        }
        div.stButton > button,
        a[data-testid="stLinkButton"] {
            background: #16866d;
            border: 1px solid #16866d;
            border-radius: 10px;
            color: white;
            font-weight: 700;
        }
        div.stButton > button:hover,
        a[data-testid="stLinkButton"]:hover {
            background: #0f6f5a;
            border-color: #0f6f5a;
            color: white;
        }
        .petpass-hero {
            background: linear-gradient(135deg, #123f42 0%, #16866d 100%);
            border-radius: 18px;
            padding: 1.5rem 1.7rem;
            margin-bottom: 1.3rem;
            color: white;
            box-shadow: 0 14px 34px rgba(18, 63, 66, 0.16);
        }
        .petpass-hero .kicker {
            color: #bff4e4;
            font-size: 0.85rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.3rem;
        }
        .petpass-hero h1 {
            color: white;
            font-size: 2.1rem;
            line-height: 1.15;
            margin: 0;
        }
        .petpass-hero p {
            color: #ecfffa;
            font-size: 1rem;
            margin: 0.55rem 0 0;
            max-width: 760px;
        }
        .petpass-panel {
            background: white;
            border: 1px solid #d8eee6;
            border-radius: 14px;
            padding: 1rem 1.1rem;
            margin: 0.7rem 0 1rem;
        }
        .petpass-muted {
            color: #5b7376;
            margin-top: -0.4rem;
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(kicker, title, subtitle):
    st.markdown(
        f"""
        <div class="petpass-hero">
            <div class="kicker">{kicker}</div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def load_tutores():
    if cloud_mode():
        result = (
            sb()
            .table("tutores")
            .select("*")
            .eq("clinica_id", current_clinic_id())
            .order("creado_en", desc=True)
            .execute()
        )
        return rows_to_df(result.data)
    return read_df("SELECT * FROM tutores ORDER BY id DESC")


def load_mascotas():
    if cloud_mode():
        mascotas = rows_to_df(
            sb()
            .table("mascotas")
            .select("*")
            .eq("clinica_id", current_clinic_id())
            .order("creado_en", desc=True)
            .execute()
            .data
        )
        tutores = load_tutores()
        if mascotas.empty:
            return mascotas
        if tutores.empty:
            mascotas["tutor_nombre"] = ""
            mascotas["tutor_telefono"] = ""
            return mascotas
        tutores_min = tutores[["id", "nombre", "telefono"]].rename(
            columns={
                "id": "tutor_id",
                "nombre": "tutor_nombre",
                "telefono": "tutor_telefono",
            }
        )
        return mascotas.merge(tutores_min, on="tutor_id", how="left")

    return read_df(
        """
        SELECT m.*, t.nombre AS tutor_nombre, t.telefono AS tutor_telefono
        FROM mascotas m
        LEFT JOIN tutores t ON t.id = m.tutor_id
        ORDER BY m.id DESC
        """
    )


def load_dashboard_pets():
    if cloud_mode():
        mascotas = load_mascotas()
        vacunas = rows_to_df(
            sb()
            .table("vacunas")
            .select("mascota_id, proxima_fecha")
            .eq("clinica_id", current_clinic_id())
            .execute()
            .data
        )
        if mascotas.empty:
            return mascotas
        if vacunas.empty:
            mascotas["proxima_fecha"] = ""
        else:
            vacunas = (
                vacunas.dropna(subset=["proxima_fecha"])
                .sort_values("proxima_fecha")
                .groupby("mascota_id", as_index=False)
                .first()
            )
            mascotas = mascotas.merge(
                vacunas,
                left_on="id",
                right_on="mascota_id",
                how="left",
            )
        mascotas = mascotas.rename(columns={"tutor_nombre": "tutor"})
        if "foto_path" not in mascotas.columns:
            mascotas["foto_path"] = ""
        if "foto_url" not in mascotas.columns:
            mascotas["foto_url"] = ""
        if "proxima_fecha" not in mascotas.columns:
            mascotas["proxima_fecha"] = ""
        return mascotas[["id", "nombre", "foto_path", "foto_url", "tutor", "proxima_fecha"]].head(6)

    return read_df(
        """
        SELECT m.id, m.nombre, m.foto_path, t.nombre AS tutor, pv.proxima_fecha
        FROM mascotas m
        LEFT JOIN tutores t ON t.id = m.tutor_id
        LEFT JOIN (
            SELECT mascota_id, MIN(proxima_fecha) AS proxima_fecha
            FROM vacunas
            WHERE proxima_fecha IS NOT NULL AND proxima_fecha != ''
            GROUP BY mascota_id
        ) pv ON pv.mascota_id = m.id
        ORDER BY m.id DESC
        LIMIT 6
        """
    )


def load_vacunas():
    if cloud_mode():
        vacunas = rows_to_df(
            sb()
            .table("vacunas")
            .select("*")
            .eq("clinica_id", current_clinic_id())
            .order("fecha_aplicada", desc=True)
            .execute()
            .data
        )
        mascotas = load_mascotas()
        if vacunas.empty:
            return vacunas
        if mascotas.empty:
            vacunas["mascota_nombre"] = ""
            vacunas["tutor_nombre"] = ""
            return vacunas
        mascotas_min = mascotas[["id", "nombre", "tutor_nombre"]].rename(
            columns={"id": "mascota_id", "nombre": "mascota_nombre"}
        )
        return vacunas.merge(mascotas_min, on="mascota_id", how="left")

    return read_df(
        """
        SELECT v.*, m.nombre AS mascota_nombre, t.nombre AS tutor_nombre
        FROM vacunas v
        LEFT JOIN mascotas m ON m.id = v.mascota_id
        LEFT JOIN tutores t ON t.id = m.tutor_id
        ORDER BY v.fecha_aplicada DESC, v.id DESC
        """
    )


def get_pet_record(mascota_id):
    if cloud_mode():
        mascota = rows_to_df(
            sb()
            .table("mascotas")
            .select("*")
            .eq("clinica_id", current_clinic_id())
            .eq("id", mascota_id)
            .limit(1)
            .execute()
            .data
        )
        if mascota.empty:
            return mascota, rows_to_df([])

        tutor_id = mascota.iloc[0].get("tutor_id")
        tutor = rows_to_df(
            sb()
            .table("tutores")
            .select("*")
            .eq("clinica_id", current_clinic_id())
            .eq("id", tutor_id)
            .limit(1)
            .execute()
            .data
        )
        if not tutor.empty:
            mascota["tutor_nombre"] = tutor.iloc[0].get("nombre", "")
            mascota["telefono"] = tutor.iloc[0].get("telefono", "")
            mascota["email"] = tutor.iloc[0].get("email", "")
            mascota["tutor_notas"] = tutor.iloc[0].get("notas", "")
        else:
            mascota["tutor_nombre"] = ""
            mascota["telefono"] = ""
            mascota["email"] = ""
            mascota["tutor_notas"] = ""
        vacunas = rows_to_df(
            sb()
            .table("vacunas")
            .select("*")
            .eq("clinica_id", current_clinic_id())
            .eq("mascota_id", mascota_id)
            .order("fecha_aplicada", desc=True)
            .execute()
            .data
        )
        return mascota, vacunas

    mascota = read_df(
        """
        SELECT m.*, t.nombre AS tutor_nombre, t.telefono, t.email, t.notas AS tutor_notas
        FROM mascotas m
        LEFT JOIN tutores t ON t.id = m.tutor_id
        WHERE m.id = ?
        """,
        (mascota_id,),
    )
    vacunas = read_df(
        "SELECT * FROM vacunas WHERE mascota_id = ? ORDER BY fecha_aplicada DESC, id DESC",
        (mascota_id,),
    )
    return mascota, vacunas


def clean_phone(phone):
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def safe_file_part(value):
    cleaned = "".join(
        ch.lower() if ch.isascii() and ch.isalnum() else "_"
        for ch in str(value or "mascota")
    )
    return "_".join(part for part in cleaned.split("_") if part) or "mascota"


def resolve_photo_path(photo_path):
    if photo_path is None:
        return None
    try:
        if pd.isna(photo_path):
            return None
    except Exception:
        pass
    photo_path = str(photo_path).strip()
    if not photo_path:
        return None
    if photo_path.startswith(("http://", "https://")):
        return photo_path
    path = Path(photo_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path if path.exists() else None


def save_pet_photo(uploaded_file, pet_id, pet_name):
    if not uploaded_file:
        return ""

    try:
        ext = Path(uploaded_file.name).suffix.lower()
        if ext not in [".jpg", ".jpeg", ".png"]:
            ext = ".jpg"
        filename = f"pet_{pet_id}_{safe_file_part(pet_name)}{ext}"
        file_path = PHOTO_DIR / filename
        file_path.write_bytes(uploaded_file.getbuffer())
        return str(file_path.relative_to(BASE_DIR))
    except Exception:
        return ""


def save_pet_photo_supabase(uploaded_file, pet_id, pet_name):
    if not uploaded_file:
        return ""
    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png"]:
        ext = ".jpg"
    filename = f"{safe_file_part(pet_name)}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
    storage_path = f"{current_clinic_id()}/{pet_id}/{filename}"
    try:
        sb().storage.from_(SUPABASE_PHOTO_BUCKET).upload(
            storage_path,
            uploaded_file.getvalue(),
            {"content-type": uploaded_file.type or "image/jpeg"},
        )
        return storage_path
    except Exception as exc:
        st.error(f"No se pudo subir la foto a Supabase Storage: {exc}")
        return ""


def signed_photo_url(storage_path):
    if not storage_path:
        return None
    if str(storage_path).startswith(("http://", "https://")):
        return storage_path
    try:
        signed = (
            sb()
            .storage.from_(SUPABASE_PHOTO_BUCKET)
            .create_signed_url(str(storage_path), 3600)
        )
        if isinstance(signed, dict):
            data = signed.get("data") or signed
            return data.get("signedUrl") or data.get("signedURL") or data.get("signed_url")
        return str(signed or "")
    except Exception:
        return None


def pet_photo_path(mascota):
    if isinstance(mascota, dict):
        value = mascota.get("foto_url") or mascota.get("foto_path")
    else:
        value = getattr(mascota, "foto_url", "") or getattr(mascota, "foto_path", "")
    if cloud_mode():
        return signed_photo_url(value)
    return resolve_photo_path(value)


def pdf_text(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value or "").encode("latin-1", "replace").decode("latin-1")


def generate_qr(mascota):
    qr_text = (
        f"Mascota: {mascota['nombre']}\n"
        f"Tutor: {mascota['tutor_nombre']}\n"
        f"Telefono: {mascota['telefono']}\n"
        "Expediente generado por PetPass MX"
    )
    file_path = QR_DIR / f"mascota_{mascota['id']}.png"
    img = qrcode.make(qr_text)
    img.save(file_path)
    return file_path


def generate_pdf(mascota, vacunas):
    file_path = PDF_DIR / f"petpass_mascota_{mascota['id']}.pdf"
    qr_path = QR_DIR / f"mascota_{mascota['id']}.png"
    photo_path = pet_photo_path(mascota)

    def section(title, x=14, w=130):
        pdf.set_x(x)
        pdf.set_fill_color(222, 244, 236)
        pdf.set_text_color(20, 63, 66)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(w, 8, pdf_text(title), ln=True, fill=True)

    def field(label, value, x=14, label_w=42, value_w=88):
        pdf.set_x(x)
        pdf.set_text_color(42, 69, 72)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(label_w, 7, pdf_text(label), border=0)
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(value_w, 7, pdf_text(value), border=0)

    def short(value, size=28):
        text = pdf_text(value)
        return text if len(text) <= size else text[: size - 3] + "..."

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_fill_color(18, 63, 66)
    pdf.rect(0, 0, 210, 38, "F")
    pdf.set_xy(14, 10)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 8, "PetPass MX - Pasaporte Digital de Mascota", ln=True)
    pdf.set_x(14)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 7, "Expediente listo para seguimiento veterinario y recordatorios.", ln=True)
    pdf.set_x(14)
    pdf.set_text_color(197, 244, 228)
    pdf.cell(0, 7, f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True)

    pdf.set_draw_color(216, 238, 230)
    pdf.set_fill_color(248, 252, 250)
    pdf.rect(154, 46, 42, 84)
    pdf.set_text_color(20, 63, 66)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(157, 49)
    pdf.cell(36, 6, "Foto", align="C")
    if photo_path:
        try:
            pdf.image(str(photo_path), x=157, y=56, w=36, h=26)
        except Exception:
            pdf.set_xy(157, 63)
            pdf.set_font("Helvetica", size=8)
            pdf.multi_cell(36, 5, "Foto no disponible", align="C")
    else:
        pdf.set_xy(157, 63)
        pdf.set_font("Helvetica", size=8)
        pdf.multi_cell(36, 5, "Sin foto registrada", align="C")

    pdf.set_xy(157, 86)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(36, 6, "QR", align="C")
    if qr_path.exists():
        try:
            pdf.image(str(qr_path), x=163, y=94, w=24)
        except Exception:
            pdf.set_xy(157, 98)
            pdf.set_font("Helvetica", size=8)
            pdf.multi_cell(36, 5, "QR no disponible", align="C")
    else:
        pdf.set_xy(157, 98)
        pdf.set_font("Helvetica", size=8)
        pdf.multi_cell(36, 5, "QR pendiente", align="C")

    pdf.set_y(46)
    section("Datos del tutor")
    field("Nombre", mascota["tutor_nombre"])
    field("Telefono", mascota["telefono"])
    field("Email", mascota["email"])

    pdf.ln(2)
    section("Datos de la mascota")
    field("Nombre", mascota["nombre"])
    field("Especie", mascota["especie"])
    field("Raza", mascota["raza"])
    field("Sexo", mascota["sexo"])
    field("Nacimiento", mascota["fecha_nacimiento"])
    field("Peso", f"{mascota['peso'] or ''} kg")

    pdf.set_y(max(pdf.get_y() + 4, 136))
    pdf.set_x(14)
    pdf.set_fill_color(222, 244, 236)
    pdf.set_text_color(20, 63, 66)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(182, 8, "Historial de vacunas", ln=True, fill=True)

    if vacunas.empty:
        pdf.set_text_color(42, 69, 72)
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 7, "Sin vacunas registradas.", ln=True)
    else:
        widths = [58, 32, 32, 60]
        headers = ["Vacuna", "Aplicada", "Proxima", "Responsable"]
        pdf.set_fill_color(22, 134, 109)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_x(14)
        for header, width in zip(headers, widths):
            pdf.cell(width, 8, header, border=0, fill=True)
        pdf.ln()
        pdf.set_text_color(42, 69, 72)
        pdf.set_font("Helvetica", size=9)
        for _, vacuna in vacunas.iterrows():
            if pdf.get_y() > 252:
                pdf.add_page()
            pdf.set_x(14)
            pdf.cell(widths[0], 7, short(vacuna["nombre_vacuna"], 34), border="B")
            pdf.cell(widths[1], 7, short(vacuna["fecha_aplicada"], 16), border="B")
            pdf.cell(widths[2], 7, short(vacuna["proxima_fecha"], 16), border="B")
            pdf.cell(widths[3], 7, short(vacuna["responsable"], 34), border="B")
            pdf.ln()

    total_pages = pdf.page_no()
    current_page = pdf.page
    pdf.set_auto_page_break(auto=False)
    for page_number in range(1, total_pages + 1):
        if hasattr(pdf, "set_page"):
            pdf.set_page(page_number)
        else:
            pdf.page = page_number
        pdf.set_draw_color(216, 238, 230)
        pdf.line(14, 279, 196, 279)
        pdf.set_xy(14, 282)
        pdf.set_text_color(92, 115, 118)
        pdf.set_font("Helvetica", size=8)
        pdf.cell(182, 5, "PetPass MX | Documento local generado para el tutor de la mascota", align="C")
    if hasattr(pdf, "set_page"):
        pdf.set_page(current_page)
    else:
        pdf.page = current_page

    pdf.output(str(file_path))
    return file_path


def whatsapp_link(mascota, vacunas):
    phone = clean_phone(mascota["telefono"])
    if not phone:
        return None

    next_vaccine = ""
    if not vacunas.empty and "proxima_fecha" in vacunas:
        upcoming = vacunas.dropna(subset=["proxima_fecha"]).sort_values("proxima_fecha")
        if not upcoming.empty:
            row = upcoming.iloc[0]
            next_vaccine = f" Su próxima vacuna es {row['nombre_vacuna']} el {row['proxima_fecha']}."

    message = (
        f"Hola {mascota['tutor_nombre']}, te recordamos el expediente de "
        f"{mascota['nombre']} en PetPass MX.{next_vaccine}"
    )
    return f"https://wa.me/52{phone}?text={quote(message)}"


def dashboard_page():
    page_header(
        "Demo local para clínicas y estéticas",
        "PetPass MX",
        "Pasaporte digital básico para controlar tutores, mascotas, vacunas y recordatorios desde una computadora.",
    )

    total_tutores, total_mascotas, total_vacunas = get_counts()
    col1, col2, col3 = st.columns(3)
    col1.metric("Tutores registrados", total_tutores)
    col2.metric("Mascotas activas", total_mascotas)
    col3.metric("Vacunas en historial", total_vacunas)

    st.markdown("### Mascotas en seguimiento")
    pets = load_dashboard_pets()
    if pets.empty:
        st.info("Aún no hay mascotas registradas.")
    else:
        for start in range(0, len(pets), 3):
            cols = st.columns(3)
            for col, pet in zip(cols, pets.iloc[start : start + 3].itertuples()):
                with col:
                    with st.container(border=True):
                        photo_path = pet_photo_path(pet)
                        if photo_path:
                            st.image(str(photo_path), use_container_width=True)
                        else:
                            st.caption("Sin foto registrada")
                        st.markdown(f"**{pet.nombre}**")
                        st.write(f"Tutor: {pet.tutor or 'Sin tutor'}")
                        st.write(f"Próxima vacuna: {pet.proxima_fecha or 'Sin fecha'}")

    st.markdown("### Agenda de próximas vacunas")
    st.markdown(
        '<p class="petpass-muted">Ordenadas por fecha para facilitar llamadas, recepción y seguimiento.</p>',
        unsafe_allow_html=True,
    )
    if cloud_mode():
        proximas = load_vacunas()
        if not proximas.empty:
            proximas = proximas.dropna(subset=["proxima_fecha"]).sort_values("proxima_fecha")
            proximas = proximas.rename(
                columns={"mascota_nombre": "mascota", "tutor_nombre": "tutor"}
            )
            columns = ["nombre_vacuna", "proxima_fecha", "responsable", "mascota", "tutor"]
            proximas = proximas[[col for col in columns if col in proximas.columns]]
    else:
        proximas = read_df(
            """
            SELECT v.nombre_vacuna, v.proxima_fecha, v.responsable,
                   m.nombre AS mascota, t.nombre AS tutor, t.telefono
            FROM vacunas v
            LEFT JOIN mascotas m ON m.id = v.mascota_id
            LEFT JOIN tutores t ON t.id = m.tutor_id
            WHERE v.proxima_fecha IS NOT NULL AND v.proxima_fecha != ''
            ORDER BY v.proxima_fecha ASC
            """
        )
    if proximas.empty:
        st.info("Todavía no hay próximas vacunas registradas.")
    else:
        st.dataframe(proximas, use_container_width=True, hide_index=True)


def tutores_page():
    page_header(
        "Clientes",
        "Tutores",
        "Registra los datos de contacto del responsable para mantener el expediente listo para seguimiento.",
    )
    st.markdown("### Nuevo tutor")
    with st.form("crear_tutor", clear_on_submit=True):
        col1, col2 = st.columns(2)
        nombre = col1.text_input("Nombre del tutor")
        telefono = col2.text_input("Teléfono")
        email = st.text_input("Email")
        notas = st.text_area("Notas")
        submitted = st.form_submit_button("Guardar tutor")

    if submitted:
        if nombre.strip():
            if cloud_mode():
                sb().table("tutores").insert(
                    {
                        "clinica_id": current_clinic_id(),
                        "nombre": nombre.strip(),
                        "telefono": telefono.strip(),
                        "email": email.strip(),
                        "notas": notas.strip(),
                    }
                ).execute()
            else:
                execute(
                    "INSERT INTO tutores (nombre, telefono, email, notas) VALUES (?, ?, ?, ?)",
                    (nombre.strip(), telefono.strip(), email.strip(), notas.strip()),
                )
            st.success("Listo: tutor guardado correctamente.")
            st.rerun()
        else:
            st.error("Escribe el nombre del tutor para continuar.")

    st.markdown("### Tutores registrados")
    st.dataframe(load_tutores(), use_container_width=True, hide_index=True)


def mascotas_page():
    page_header(
        "Pacientes",
        "Mascotas",
        "Vincula cada mascota con su tutor para construir su pasaporte digital.",
    )
    tutores = load_tutores()
    if tutores.empty:
        st.info("Primero crea un tutor para poder registrar mascotas.")
        return

    tutor_options = {
        f"{row.nombre} - {row.telefono or 'sin teléfono'}": row.id
        for row in tutores.itertuples()
    }

    st.markdown("### Nueva mascota")
    with st.form("crear_mascota", clear_on_submit=True):
        tutor_label = st.selectbox("Tutor", list(tutor_options.keys()))
        col1, col2 = st.columns(2)
        nombre = col1.text_input("Nombre de la mascota")
        especie = col2.selectbox("Especie", ["Perro", "Gato", "Otra"])
        col3, col4 = st.columns(2)
        raza = col3.text_input("Raza")
        sexo = col4.selectbox("Sexo", ["Hembra", "Macho", "No especificado"])
        col5, col6 = st.columns(2)
        fecha_nacimiento = col5.date_input("Fecha de nacimiento", value=None)
        peso = col6.number_input("Peso kg", min_value=0.0, step=0.1)
        foto = st.file_uploader("Foto opcional de la mascota", type=["jpg", "jpeg", "png"])
        notas = st.text_area("Notas")
        submitted = st.form_submit_button("Guardar mascota")

    if submitted:
        if nombre.strip():
            if cloud_mode():
                created = (
                    sb()
                    .table("mascotas")
                    .insert(
                        {
                            "clinica_id": current_clinic_id(),
                            "tutor_id": tutor_options[tutor_label],
                            "nombre": nombre.strip(),
                            "especie": especie,
                            "raza": raza.strip(),
                            "sexo": sexo,
                            "fecha_nacimiento": str(fecha_nacimiento) if fecha_nacimiento else None,
                            "peso": peso,
                            "notas": notas.strip(),
                        }
                    )
                    .execute()
                )
                mascota_id = created.data[0]["id"] if created.data else None
                foto_url = save_pet_photo_supabase(foto, mascota_id, nombre.strip()) if mascota_id else ""
                if foto_url:
                    sb().table("mascotas").update({"foto_url": foto_url}).eq(
                        "id", mascota_id
                    ).eq("clinica_id", current_clinic_id()).execute()
            else:
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO mascotas
                        (tutor_id, nombre, especie, raza, sexo, fecha_nacimiento, peso, foto_path, notas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tutor_options[tutor_label],
                            nombre.strip(),
                            especie,
                            raza.strip(),
                            sexo,
                            str(fecha_nacimiento) if fecha_nacimiento else "",
                            peso,
                            "",
                            notas.strip(),
                        ),
                    )
                    mascota_id = cur.lastrowid
                    foto_path = save_pet_photo(foto, mascota_id, nombre.strip())
                    if foto_path:
                        cur.execute(
                            "UPDATE mascotas SET foto_path = ? WHERE id = ?",
                            (foto_path, mascota_id),
                        )
                    conn.commit()
            st.success("Listo: mascota agregada al expediente.")
            st.rerun()
        else:
            st.error("Escribe el nombre de la mascota para continuar.")

    st.markdown("### Mascotas registradas")
    mascotas_registradas = load_mascotas()
    st.dataframe(mascotas_registradas, use_container_width=True, hide_index=True)

    if not mascotas_registradas.empty:
        st.markdown("### Agregar o cambiar foto")
        mascota_foto_options = {
            f"{row.nombre} - Tutor: {row.tutor_nombre}": row.id
            for row in mascotas_registradas.itertuples()
        }
        with st.form("actualizar_foto_mascota", clear_on_submit=True):
            mascota_foto_label = st.selectbox(
                "Mascota registrada",
                list(mascota_foto_options.keys()),
            )
            foto_existente = st.file_uploader(
                "Foto para mascota registrada",
                type=["jpg", "jpeg", "png"],
            )
            actualizar_foto = st.form_submit_button("Guardar foto")

        if actualizar_foto:
            if foto_existente:
                mascota_id = mascota_foto_options[mascota_foto_label]
                mascota_row = mascotas_registradas[
                    mascotas_registradas["id"] == mascota_id
                ].iloc[0]
                if cloud_mode():
                    foto_path = save_pet_photo_supabase(
                        foto_existente,
                        mascota_id,
                        mascota_row["nombre"],
                    )
                    if foto_path:
                        sb().table("mascotas").update({"foto_url": foto_path}).eq(
                            "id", mascota_id
                        ).eq("clinica_id", current_clinic_id()).execute()
                else:
                    foto_path = save_pet_photo(
                        foto_existente,
                        mascota_id,
                        mascota_row["nombre"],
                    )
                    if foto_path:
                        execute(
                            "UPDATE mascotas SET foto_path = ? WHERE id = ?",
                            (foto_path, mascota_id),
                        )
                if foto_path:
                    st.success("Listo: foto actualizada correctamente.")
                    st.rerun()
                else:
                    st.error("No se pudo guardar la foto. Intenta con otra imagen.")
            else:
                st.error("Selecciona una foto para guardar.")


def vacunas_page():
    page_header(
        "Salud preventiva",
        "Vacunas",
        "Registra aplicaciones y próximas fechas para convertir el seguimiento en una oportunidad de recompra.",
    )
    mascotas = load_mascotas()
    if mascotas.empty:
        st.info("Primero crea una mascota para poder registrar vacunas.")
        return

    mascota_options = {
        f"{row.nombre} - Tutor: {row.tutor_nombre}": row.id
        for row in mascotas.itertuples()
    }

    st.markdown("### Nueva vacuna")
    with st.form("crear_vacuna", clear_on_submit=True):
        mascota_label = st.selectbox("Mascota", list(mascota_options.keys()))
        col1, col2 = st.columns(2)
        nombre_vacuna = col1.text_input("Nombre de vacuna")
        responsable = col2.text_input("Responsable")
        col3, col4 = st.columns(2)
        fecha_aplicada = col3.date_input("Fecha aplicada", value=None)
        proxima_fecha = col4.date_input("Próxima fecha", value=None)
        notas = st.text_area("Notas")
        submitted = st.form_submit_button("Registrar vacuna")

    if submitted:
        if nombre_vacuna.strip():
            if cloud_mode():
                sb().table("vacunas").insert(
                    {
                        "clinica_id": current_clinic_id(),
                        "mascota_id": mascota_options[mascota_label],
                        "nombre_vacuna": nombre_vacuna.strip(),
                        "fecha_aplicada": str(fecha_aplicada) if fecha_aplicada else None,
                        "proxima_fecha": str(proxima_fecha) if proxima_fecha else None,
                        "responsable": responsable.strip(),
                        "notas": notas.strip(),
                    }
                ).execute()
            else:
                execute(
                    """
                    INSERT INTO vacunas
                    (mascota_id, nombre_vacuna, fecha_aplicada, proxima_fecha, responsable, notas)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mascota_options[mascota_label],
                        nombre_vacuna.strip(),
                        str(fecha_aplicada) if fecha_aplicada else "",
                        str(proxima_fecha) if proxima_fecha else "",
                        responsable.strip(),
                        notas.strip(),
                    ),
                )
            st.success("Listo: vacuna registrada en el pasaporte.")
            st.rerun()
        else:
            st.error("Escribe el nombre de la vacuna para continuar.")

    st.markdown("### Historial de vacunas")
    st.dataframe(load_vacunas(), use_container_width=True, hide_index=True)


def expediente_page():
    page_header(
        "Pasaporte digital",
        "Expediente de mascota",
        "Consulta datos del tutor, historial de vacunas y genera material listo para compartir.",
    )
    mascotas = load_mascotas()
    if mascotas.empty:
        st.info("Primero crea una mascota o carga datos demo para ver un expediente completo.")
        return

    mascota_options = {
        f"{row.nombre} - Tutor: {row.tutor_nombre}": row.id
        for row in mascotas.itertuples()
    }
    selected = st.selectbox("Seleccionar mascota", list(mascota_options.keys()))
    mascota_df, vacunas = get_pet_record(mascota_options[selected])

    if mascota_df.empty:
        st.error("No se encontró la mascota.")
        return

    mascota = mascota_df.iloc[0].to_dict()

    col_photo, col1, col2 = st.columns([0.9, 1.2, 1.2])
    with col_photo:
        with st.container(border=True):
            st.markdown("### Foto")
            photo_path = pet_photo_path(mascota)
            if photo_path:
                st.image(str(photo_path), use_container_width=True)
            else:
                st.write("Sin foto registrada")
    with col1:
        with st.container(border=True):
            st.markdown("### Datos de mascota")
            st.write(f"**Nombre:** {mascota['nombre']}")
            st.write(f"**Especie:** {mascota['especie']}")
            st.write(f"**Raza:** {mascota['raza']}")
            st.write(f"**Sexo:** {mascota['sexo']}")
            st.write(f"**Nacimiento:** {mascota['fecha_nacimiento']}")
            st.write(f"**Peso:** {mascota['peso']} kg")
    with col2:
        with st.container(border=True):
            st.markdown("### Datos de tutor")
            st.write(f"**Nombre:** {mascota['tutor_nombre']}")
            st.write(f"**Teléfono:** {mascota['telefono']}")
            st.write(f"**Email:** {mascota['email']}")

    st.markdown("### Historial de vacunas")
    st.dataframe(vacunas, use_container_width=True, hide_index=True)

    col_qr, col_pdf = st.columns(2)
    with col_qr:
        if st.button("Generar QR del expediente"):
            qr_path = generate_qr(mascota)
            st.success(f"Listo: QR generado en {qr_path}")
            st.image(str(qr_path), width=180)

    with col_pdf:
        if st.button("Generar PDF para entregar"):
            pdf_path = generate_pdf(mascota, vacunas)
            st.success(f"Listo: PDF generado en {pdf_path}")
            try:
                st.download_button(
                    "Descargar PDF",
                    data=pdf_path.read_bytes(),
                    file_name=pdf_path.name,
                    mime="application/pdf",
                )
            except Exception:
                pass

    qr_path = QR_DIR / f"mascota_{mascota['id']}.png"
    if qr_path.exists():
        st.image(str(qr_path), width=180)

    link = whatsapp_link(mascota, vacunas)
    if link:
        st.link_button("Abrir recordatorio en WhatsApp Web", link)
    else:
        st.info("Agrega teléfono del tutor para generar el link de WhatsApp.")


def demo_exists():
    if cloud_mode():
        result = (
            sb()
            .table("tutores")
            .select("id")
            .eq("clinica_id", current_clinic_id())
            .eq("email", "maria@demo.petpass.mx")
            .limit(1)
            .execute()
        )
        return bool(result.data)

    with get_conn() as conn:
        result = conn.execute(
            "SELECT COUNT(*) FROM tutores WHERE email LIKE '%@demo.petpass.mx'"
        ).fetchone()[0]
    return result > 0


def load_demo_data():
    if cloud_mode():
        clinic = ensure_demo_clinic()
        if not clinic:
            return False
        clinic_id = clinic["id"]
        st.session_state["clinica_id"] = clinic_id
        st.session_state["clinica_nombre"] = clinic["nombre"]

        found = (
            sb()
            .table("tutores")
            .select("id")
            .eq("clinica_id", clinic_id)
            .eq("email", "maria@demo.petpass.mx")
            .limit(1)
            .execute()
        )
        if found.data:
            return False

        tutores = (
            sb()
            .table("tutores")
            .insert(
                [
                    {
                        "clinica_id": clinic_id,
                        "nombre": "Maria Lopez",
                        "telefono": "5512345678",
                        "email": "maria@demo.petpass.mx",
                        "notas": "Cliente demo",
                    },
                    {
                        "clinica_id": clinic_id,
                        "nombre": "Carlos Perez",
                        "telefono": "5587654321",
                        "email": "carlos@demo.petpass.mx",
                        "notas": "Cliente demo",
                    },
                ]
            )
            .execute()
            .data
        )
        maria_id = tutores[0]["id"]
        carlos_id = tutores[1]["id"]

        pets = (
            sb()
            .table("mascotas")
            .insert(
                [
                    {
                        "clinica_id": clinic_id,
                        "tutor_id": maria_id,
                        "nombre": "Luna",
                        "especie": "Perro",
                        "raza": "French Poodle",
                        "sexo": "Hembra",
                        "fecha_nacimiento": "2021-04-15",
                        "peso": 6.5,
                        "notas": "Nerviosa",
                    },
                    {
                        "clinica_id": clinic_id,
                        "tutor_id": maria_id,
                        "nombre": "Rocky",
                        "especie": "Perro",
                        "raza": "Mestizo",
                        "sexo": "Macho",
                        "fecha_nacimiento": "2020-08-20",
                        "peso": 18.0,
                        "notas": "Muy activo",
                    },
                    {
                        "clinica_id": clinic_id,
                        "tutor_id": carlos_id,
                        "nombre": "Michi",
                        "especie": "Gato",
                        "raza": "Europeo domestico",
                        "sexo": "Macho",
                        "fecha_nacimiento": "2022-01-10",
                        "peso": 4.2,
                        "notas": "Tranquilo",
                    },
                ]
            )
            .execute()
            .data
        )

        sb().table("vacunas").insert(
            [
                {
                    "clinica_id": clinic_id,
                    "mascota_id": pets[0]["id"],
                    "nombre_vacuna": "Rabia",
                    "fecha_aplicada": "2026-01-12",
                    "proxima_fecha": "2027-01-12",
                    "responsable": "Dra. Ana Ruiz",
                    "notas": "Sin reaccion",
                },
                {
                    "clinica_id": clinic_id,
                    "mascota_id": pets[1]["id"],
                    "nombre_vacuna": "Multiple canina",
                    "fecha_aplicada": "2026-02-05",
                    "proxima_fecha": "2027-02-05",
                    "responsable": "Dr. Luis Mora",
                    "notas": "",
                },
                {
                    "clinica_id": clinic_id,
                    "mascota_id": pets[2]["id"],
                    "nombre_vacuna": "Triple felina",
                    "fecha_aplicada": "2026-03-18",
                    "proxima_fecha": "2027-03-18",
                    "responsable": "Dra. Ana Ruiz",
                    "notas": "",
                },
            ]
        ).execute()
        return True

    if demo_exists():
        return False

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tutores (nombre, telefono, email, notas)
            VALUES (?, ?, ?, ?)
            """,
            ("María López", "5512345678", "maria@demo.petpass.mx", "Cliente demo"),
        )
        maria_id = cur.lastrowid
        cur.execute(
            """
            INSERT INTO tutores (nombre, telefono, email, notas)
            VALUES (?, ?, ?, ?)
            """,
            ("Carlos Pérez", "5587654321", "carlos@demo.petpass.mx", "Cliente demo"),
        )
        carlos_id = cur.lastrowid

        pets = [
            (maria_id, "Luna", "Perro", "French Poodle", "Hembra", "2021-04-15", 6.5, "Nerviosa"),
            (maria_id, "Rocky", "Perro", "Mestizo", "Macho", "2020-08-20", 18.0, "Muy activo"),
            (carlos_id, "Michi", "Gato", "Europeo doméstico", "Macho", "2022-01-10", 4.2, "Tranquilo"),
        ]
        pet_ids = []
        for pet in pets:
            cur.execute(
                """
                INSERT INTO mascotas
                (tutor_id, nombre, especie, raza, sexo, fecha_nacimiento, peso, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                pet,
            )
            pet_ids.append(cur.lastrowid)

        vaccines = [
            (pet_ids[0], "Rabia", "2026-01-12", "2027-01-12", "Dra. Ana Ruiz", "Sin reacción"),
            (pet_ids[1], "Múltiple canina", "2026-02-05", "2027-02-05", "Dr. Luis Mora", ""),
            (pet_ids[2], "Triple felina", "2026-03-18", "2027-03-18", "Dra. Ana Ruiz", ""),
        ]
        cur.executemany(
            """
            INSERT INTO vacunas
            (mascota_id, nombre_vacuna, fecha_aplicada, proxima_fecha, responsable, notas)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            vaccines,
        )
        conn.commit()
    return True


def datos_demo_page():
    page_header(
        "Modo presentación",
        "Datos demo",
        "Carga un ejemplo rápido para mostrar PetPass MX sin capturar información desde cero.",
    )
    if cloud_mode() and not st.session_state.get("modo_demo"):
        st.info("Los datos demo en Supabase solo están disponibles dentro de la demo pública.")
        return
    st.write("Incluye 2 tutores, 3 mascotas y 3 vacunas.")
    demo_button = "Crear datos demo en Supabase" if cloud_mode() else "Cargar datos demo"
    if st.button(demo_button):
        loaded = load_demo_data()
        if loaded:
            st.success("Listo: datos demo cargados para presentar la app.")
            st.rerun()
        else:
            st.info("Los datos demo ya existen, no se duplicaron.")


def main():
    st.set_page_config(page_title="PetPass MX", layout="wide")
    apply_visual_style()
    init_db()

    if supabase_enabled() and not current_clinic_id():
        show_clinic_gate()
        return

    st.sidebar.markdown("## PetPass MX")
    st.sidebar.caption("Demo local para veterinarias y estéticas caninas")
    if cloud_mode():
        st.sidebar.caption(f"Clinica: {st.session_state.get('clinica_nombre', 'Sin nombre')}")
        if st.session_state.get("modo_demo"):
            st.sidebar.caption("Modo demo pública")
        else:
            st.sidebar.caption("Modo Supabase Auth")
        if st.sidebar.button("Cerrar sesión"):
            try:
                if st.session_state.get("is_authenticated"):
                    sb().auth.sign_out()
            except Exception:
                pass
            clear_session_state()
            st.rerun()
    else:
        st.sidebar.caption("Modo SQLite local")
    page = st.sidebar.radio(
        "Navegación",
        ["Dashboard", "Tutores", "Mascotas", "Vacunas", "Expediente", "Datos demo"],
    )
    if st.session_state.get("modo_demo"):
        st.warning("Demo pública con datos ficticios. No ingresar datos reales.")
    st.sidebar.caption("SQLite local o Supabase seguro")

    if page == "Dashboard":
        dashboard_page()
    elif page == "Tutores":
        tutores_page()
    elif page == "Mascotas":
        mascotas_page()
    elif page == "Vacunas":
        vacunas_page()
    elif page == "Expediente":
        expediente_page()
    elif page == "Datos demo":
        datos_demo_page()


if __name__ == "__main__":
    main()
