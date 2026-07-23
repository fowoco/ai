from pathlib import Path

from PIL import Image, ImageDraw

from app.documents.hwp5 import Hwp5BinaryDocument, Hwp5DocumentService

INTEGRATED_TEMPLATE_ID = "immigration_integrated_application_v34"


def _signature(path: Path) -> None:
    canvas = Image.new("RGBA", (700, 200), (255, 255, 255, 0))
    draw = ImageDraw.Draw(canvas)
    draw.line((20, 150, 220, 40, 430, 155, 680, 30), fill="black", width=12)
    canvas.save(path)


def test_registry_loads_and_identifies_all_bundled_templates() -> None:
    service = Hwp5DocumentService()
    templates = service.templates()

    assert len(templates) == 4
    for template in templates:
        assert service.identify(template.source_path).template_id == template.template_id


def test_generate_text_checkbox_photo_and_signature(tmp_path: Path) -> None:
    service = Hwp5DocumentService()
    photo = tmp_path / "photo.jpg"
    signature = tmp_path / "signature.png"
    output = tmp_path / "filled.hwp"
    Image.new("RGB", (350, 450), "royalblue").save(photo)
    _signature(signature)

    result = service.generate(
        INTEGRATED_TEMPLATE_ID,
        output,
        values={
            "family_name": "HONG",
            "given_names": "GILDONG",
            "application_stay_extension": True,
        },
        images={
            "photo": photo,
            "applicant_signature": signature,
        },
    )

    assert result.destination == output.resolve()
    assert result.template_id == INTEGRATED_TEMPLATE_ID
    assert result.changed_fields == (
        "family_name",
        "given_names",
        "application_stay_extension",
        "photo",
        "applicant_signature",
    )

    reopened = Hwp5BinaryDocument(output)
    assert reopened.paragraphs()[46].text == "HONG"
    assert reopened.paragraphs()[47].text == "GILDONG"
    assert "[√ " in reopened.paragraphs()[24].text
    assert [image.extension for image in reopened.embedded_images()] == ["jpg", "png"]
