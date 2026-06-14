# PetPass MX

## Crear entorno virtual

```powershell
python -m venv .venv
```

## Activar entorno

```powershell
.venv\Scripts\activate
```

## Instalar dependencias

```powershell
pip install -r requirements.txt
```

## Correr app

```powershell
streamlit run app.py
```

## Cómo probar la demo

1. Abre la app.
2. Entra a `Datos demo` y presiona `Cargar datos demo`.
3. Revisa `Dashboard`.
4. Entra a `Expediente`, selecciona una mascota y genera QR/PDF.
5. Abre el link de WhatsApp.
