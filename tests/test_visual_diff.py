import pytest
from pathlib import Path
from PIL import Image, ImageDraw
from hwp_mcp.compare import svg_to_png, generate_visual_diff
from hwp_mcp.hwpx import DocumentError
from hwp_mcp.vision import create_vision_detail_crops

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


def test_vision_detail_crops_only_edited_bands(tmp_path):
    images = []
    for name, color in (
        ("original", "white"),
        ("modified", "gray"),
        ("diff", "red"),
    ):
        path = tmp_path / f"{name}.png"
        Image.new("RGB", (100, 900), color).save(path)
        images.append(path)

    details = create_vision_detail_crops(
        page_number=1,
        original_path=images[0],
        modified_path=images[1],
        diff_path=images[2],
        field_regions={
            "top-field": [10, 50, 30, 80],
            "bottom-field": [10, 650, 30, 680],
        },
        output_dir=tmp_path / "details",
    )

    assert [detail["bbox"] for detail in details] == [
        [0, 0, 100, 324],
        [0, 576, 100, 900],
    ]
    assert all(
        Path(detail[kind]).is_file()
        for detail in details
        for kind in ("original", "modified", "diff")
    )


def test_vision_detail_crops_skip_small_readable_page(tmp_path):
    images = []
    for name in ("original", "modified", "diff"):
        path = tmp_path / f"{name}.png"
        Image.new("RGB", (100, 300), "white").save(path)
        images.append(path)

    details = create_vision_detail_crops(
        page_number=1,
        original_path=images[0],
        modified_path=images[1],
        diff_path=images[2],
        field_regions={"field": [10, 10, 30, 30]},
        output_dir=tmp_path / "details",
    )

    assert details == []


def test_vision_detail_crops_cap_three_bands_per_page(tmp_path):
    images = []
    for name in ("original", "modified", "diff"):
        path = tmp_path / f"{name}.png"
        Image.new("RGB", (100, 2000), "white").save(path)
        images.append(path)

    details = create_vision_detail_crops(
        page_number=1,
        original_path=images[0],
        modified_path=images[1],
        diff_path=images[2],
        field_regions={
            "field-1": [10, 100, 30, 120],
            "field-2": [10, 700, 30, 720],
            "field-3": [10, 1300, 30, 1320],
            "field-4": [10, 1900, 30, 1920],
        },
        output_dir=tmp_path / "details",
    )

    assert len(details) == 3


def test_vision_detail_crops_reject_mismatched_page_sizes(tmp_path):
    original = tmp_path / "original.png"
    modified = tmp_path / "modified.png"
    diff = tmp_path / "diff.png"
    Image.new("RGB", (100, 900), "white").save(original)
    Image.new("RGB", (100, 800), "white").save(modified)
    Image.new("RGB", (100, 900), "white").save(diff)

    with pytest.raises(DocumentError, match="크기가 다릅니다"):
        create_vision_detail_crops(
            page_number=1,
            original_path=original,
            modified_path=modified,
            diff_path=diff,
            field_regions={"field": [10, 10, 30, 30]},
            output_dir=tmp_path / "details",
        )
