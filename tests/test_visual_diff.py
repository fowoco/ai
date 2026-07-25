import pytest
from pathlib import Path
from PIL import Image, ImageDraw
from hwp_mcp.compare import svg_to_png, generate_visual_diff

def test_svg_to_png_conversion(tmp_path):
    svg_content = """<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
        <rect width="100" height="100" fill="blue"/>
    </svg>"""
    svg_path = tmp_path / "sample.svg"
    png_path = tmp_path / "sample.png"
    svg_path.write_text(svg_content, encoding="utf-8")

    result_path = svg_to_png(svg_path, png_path)
    assert result_path.exists()
    
    img = Image.open(result_path)
    assert img.size == (100, 100)

def test_generate_visual_diff_red_highlight(tmp_path):
    img1_path = tmp_path / "orig.png"
    img2_path = tmp_path / "mod.png"
    diff_path = tmp_path / "diff.png"

    # 100x100 하얀 바탕 원본 이미지
    im1 = Image.new("RGB", (100, 100), "white")
    im1.save(img1_path)

    # 100x100 하얀 바탕에 (20,20)-(40,40) 영역에 검은색 사각형이 그려진 수정본 이미지
    im2 = Image.new("RGB", (100, 100), "white")
    draw = ImageDraw.Draw(im2)
    draw.rectangle([20, 20, 40, 40], fill="black")
    im2.save(img2_path)

    result = generate_visual_diff(img1_path, img2_path, diff_path)

    assert result["has_diff"] is True
    assert result["diff_bbox"] is not None
    assert Path(result["diff_png_path"]).exists()

    # 하이라이트된 이미지에서 빨간색 박스가 그려졌는지 확인 (빨간색 픽셀 존재)
    diff_img = Image.open(diff_path)
    colors = diff_img.getcolors(maxcolors=10000)
    has_red = any(c[1] == (255, 0, 0) for c in colors if c)
    assert has_red is True
