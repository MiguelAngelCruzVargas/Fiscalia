# Proyecto: FISCAL-IA - Extracción y resumen de PDFs

Este mini-proyecto extrae texto de los PDFs presentes en la carpeta y genera archivos `.txt` para su análisis. Luego, se resumirán las ideas para proponer un plan de monetización y roadmap.

## Estructura
- `extract_pdfs.py`: Script para extraer texto usando pypdf y fallback pdfminer.six.
- `requirements.txt`: Dependencias de Python.

## Pasos rápidos

1) Crear y activar un entorno virtual (Windows PowerShell):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) Instalar dependencias:

```powershell
pip install -r requirements.txt
```

3) Extraer texto de los PDFs de la carpeta actual:

```powershell
python .\extract_pdfs.py .
```

Esto producirá archivos `.txt` junto a cada PDF.

## Notas
- Si un PDF es una imagen escaneada, estos métodos no extraerán texto. En ese caso se necesitará OCR (por ejemplo, `tesseract-ocr` + `pytesseract`). Si lo detectamos, te propondré activarlo.

## Documentación relacionada
- Guía de integración con SAT-CFDI (alcance, decisiones y plan): `docs/satcfdi_integracion.md`
