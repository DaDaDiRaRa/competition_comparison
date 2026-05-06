import subprocess
import tempfile
from pathlib import Path


def _rasterize_with_pdftoppm(pdf_path: Path, out_dir: Path, dpi: int) -> list[Path]:
    prefix = out_dir / "page"
    cmd = [
        "pdftoppm",
        "-r", str(dpi),
        "-png",
        str(pdf_path),
        str(prefix),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {result.stderr}")
    pages = sorted(out_dir.glob("page-*.png"))
    if not pages:
        pages = sorted(out_dir.glob("page*.png"))
    return pages


def _rasterize_with_pdf2image(pdf_path: Path, out_dir: Path, dpi: int) -> list[Path]:
    from pdf2image import convert_from_path
    images = convert_from_path(str(pdf_path), dpi=dpi)
    paths = []
    for i, img in enumerate(images):
        p = out_dir / f"page-{i+1:04d}.png"
        img.save(str(p), "PNG")
        paths.append(p)
    return paths


def rasterize_pdf(pdf_path: Path, dpi: int, out_dir: Path | None = None) -> tuple[list[Path], Path]:
    """
    Convert PDF to PNG images. Returns (image_paths, temp_dir).
    Caller is responsible for cleanup of temp_dir if out_dir was None.
    """
    if out_dir is None:
        tmp = tempfile.mkdtemp(prefix="comp_pdf_")
        out_dir = Path(tmp)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        pages = _rasterize_with_pdftoppm(pdf_path, out_dir, dpi)
        if pages:
            return pages, out_dir
    except (FileNotFoundError, RuntimeError):
        pass

    pages = _rasterize_with_pdf2image(pdf_path, out_dir, dpi)
    return pages, out_dir
