from pathlib import Path
from datetime import datetime
from urllib.parse import quote
import sqlite3

import pandas as pd
import qrcode
import streamlit as st
from fpdf import FPDF


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
QR_DIR = BASE_DIR / "storage" / "qr"
PDF_DIR = BASE_DIR / "storage" / "pdf"
PHOTO_DIR = BASE_DIR / "storage" / "photos"
EXPORTS_DIR = BASE_DIR / "exports"
DB_PATH = DATA_DIR / "petpass.db"


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
    return read_df("SELECT * FROM tutores ORDER BY id DESC")


def load_mascotas():
    return read_df(
        """
        SELECT m.*, t.nombre AS tutor_nombre, t.telefono AS tutor_telefono
        FROM mascotas m
        LEFT JOIN tutores t ON t.id = m.tutor_id
        ORDER BY m.id DESC
        """
    )


def load_dashboard_pets():
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


def pet_photo_path(mascota):
    if isinstance(mascota, dict):
        return resolve_photo_path(mascota.get("foto_path"))
    return resolve_photo_path(getattr(mascota, "foto_path", ""))


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
    pdf.rect(154, 46, 42, 72)
    pdf.set_text_color(20, 63, 66)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(157, 49)
    pdf.cell(36, 6, "Foto", align="C")
    if photo_path:
        try:
            pdf.image(str(photo_path), x=157, y=56, w=36, h=28)
        except Exception:
            pdf.set_xy(157, 63)
            pdf.set_font("Helvetica", size=8)
            pdf.multi_cell(36, 5, "Foto no disponible", align="C")
    else:
        pdf.set_xy(157, 63)
        pdf.set_font("Helvetica", size=8)
        pdf.multi_cell(36, 5, "Sin foto registrada", align="C")

    pdf.set_xy(157, 88)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(36, 6, "QR", align="C")
    if qr_path.exists():
        try:
            pdf.image(str(qr_path), x=162, y=96, w=26)
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

    pdf.set_y(max(pdf.get_y() + 4, 124))
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
            if pdf.get_y() > 260:
                pdf.add_page()
            pdf.set_x(14)
            pdf.cell(widths[0], 7, short(vacuna["nombre_vacuna"], 34), border="B")
            pdf.cell(widths[1], 7, short(vacuna["fecha_aplicada"], 16), border="B")
            pdf.cell(widths[2], 7, short(vacuna["proxima_fecha"], 16), border="B")
            pdf.cell(widths[3], 7, short(vacuna["responsable"], 34), border="B")
            pdf.ln()

    pdf.set_y(-18)
    pdf.set_text_color(92, 115, 118)
    pdf.set_font("Helvetica", size=8)
    pdf.cell(0, 6, "PetPass MX | Documento local generado para el tutor de la mascota", align="C")

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
        f"{row.nombre} - {row.telefono or 'sin teléfono'}": int(row.id)
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
            f"{row.nombre} - Tutor: {row.tutor_nombre}": int(row.id)
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
        f"{row.nombre} - Tutor: {row.tutor_nombre}": int(row.id)
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
        f"{row.nombre} - Tutor: {row.tutor_nombre}": int(row.id)
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

    qr_path = QR_DIR / f"mascota_{mascota['id']}.png"
    if qr_path.exists():
        st.image(str(qr_path), width=180)

    link = whatsapp_link(mascota, vacunas)
    if link:
        st.link_button("Abrir recordatorio en WhatsApp Web", link)
    else:
        st.info("Agrega teléfono del tutor para generar el link de WhatsApp.")


def demo_exists():
    with get_conn() as conn:
        result = conn.execute(
            "SELECT COUNT(*) FROM tutores WHERE email LIKE '%@demo.petpass.mx'"
        ).fetchone()[0]
    return result > 0


def load_demo_data():
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
    st.write("Incluye 2 tutores, 3 mascotas y 3 vacunas.")
    if st.button("Cargar datos demo"):
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

    st.sidebar.markdown("## PetPass MX")
    st.sidebar.caption("Demo local para veterinarias y estéticas caninas")
    page = st.sidebar.radio(
        "Navegación",
        ["Dashboard", "Tutores", "Mascotas", "Vacunas", "Expediente", "Datos demo"],
    )
    st.sidebar.caption("SQLite local | Sin nube | Sin login")

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
