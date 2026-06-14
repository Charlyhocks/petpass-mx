from pathlib import Path
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
EXPORTS_DIR = BASE_DIR / "exports"
DB_PATH = DATA_DIR / "petpass.db"


def ensure_dirs():
    for folder in [DATA_DIR, QR_DIR, PDF_DIR, EXPORTS_DIR]:
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

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "PetPass MX - Pasaporte Digital", ln=True)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Tutor", ln=True)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 7, f"Nombre: {mascota['tutor_nombre'] or ''}", ln=True)
    pdf.cell(0, 7, f"Telefono: {mascota['telefono'] or ''}", ln=True)
    pdf.cell(0, 7, f"Email: {mascota['email'] or ''}", ln=True)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Mascota", ln=True)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 7, f"Nombre: {mascota['nombre'] or ''}", ln=True)
    pdf.cell(0, 7, f"Especie: {mascota['especie'] or ''}", ln=True)
    pdf.cell(0, 7, f"Raza: {mascota['raza'] or ''}", ln=True)
    pdf.cell(0, 7, f"Sexo: {mascota['sexo'] or ''}", ln=True)
    pdf.cell(0, 7, f"Fecha nacimiento: {mascota['fecha_nacimiento'] or ''}", ln=True)
    pdf.cell(0, 7, f"Peso: {mascota['peso'] or ''}", ln=True)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Historial de vacunas", ln=True)
    pdf.set_font("Helvetica", size=9)

    if vacunas.empty:
        pdf.cell(0, 7, "Sin vacunas registradas.", ln=True)
    else:
        for _, vacuna in vacunas.iterrows():
            linea = (
                f"{vacuna['nombre_vacuna']} | Aplicada: {vacuna['fecha_aplicada'] or ''} | "
                f"Proxima: {vacuna['proxima_fecha'] or ''} | Resp.: {vacuna['responsable'] or ''}"
            )
            pdf.multi_cell(0, 6, linea)

    if qr_path.exists():
        pdf.ln(5)
        pdf.image(str(qr_path), x=155, y=20, w=35)

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
        notas = st.text_area("Notas")
        submitted = st.form_submit_button("Guardar mascota")

    if submitted:
        if nombre.strip():
            execute(
                """
                INSERT INTO mascotas
                (tutor_id, nombre, especie, raza, sexo, fecha_nacimiento, peso, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tutor_options[tutor_label],
                    nombre.strip(),
                    especie,
                    raza.strip(),
                    sexo,
                    str(fecha_nacimiento) if fecha_nacimiento else "",
                    peso,
                    notas.strip(),
                ),
            )
            st.success("Listo: mascota agregada al expediente.")
            st.rerun()
        else:
            st.error("Escribe el nombre de la mascota para continuar.")

    st.markdown("### Mascotas registradas")
    st.dataframe(load_mascotas(), use_container_width=True, hide_index=True)


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

    col1, col2 = st.columns(2)
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
