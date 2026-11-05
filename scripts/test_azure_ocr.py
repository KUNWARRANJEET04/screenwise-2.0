import argparse
import json
import logging
from pathlib import Path

from screenwise.config import settings
from screenwise.ocr.preprocessor import preprocess_image
from screenwise.providers.azure_vision import AzureVisionOCRProvider


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test Microsoft Azure AI Vision OCR."
    )
    parser.add_argument(
        "image",
        help="Path to an iPhone Screen Time screenshot.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    image_path = Path(args.image).expanduser().resolve()

    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if not settings.azure_vision_endpoint or not settings.azure_vision_key:
        raise RuntimeError(
            "Azure configuration is missing. "
            "Check AZURE_VISION_ENDPOINT and AZURE_VISION_KEY in .env."
        )

    print(f"\nImage: {image_path.name}")
    print("Preprocessing image...")

    processed = preprocess_image(image_path.read_bytes())

    print(
        f"Image dimensions: "
        f"{processed.original_width}x{processed.original_height}"
    )
    print("Calling Microsoft Azure OCR...")

    provider = AzureVisionOCRProvider()

    result = provider.extract(
        image_bytes=processed.image_bytes,
        original_filename=image_path.name,
    )

    output_dir = settings.processed_dir / "azure_ocr"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{image_path.stem}_ocr.json"

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(result, file, indent=2, ensure_ascii=False)

    print("\n========== AZURE OCR RESULT ==========")
    print(f"Provider: {result['provider']}")
    print(f"Model: {result['model_name']}")
    print(f"Detected lines: {len(result['ocr_lines'])}")
    print(f"Confidence: {result['confidence']}")

    print("\n---------- EXTRACTED TEXT ----------")

    if result["ocr_text"]:
        print(result["ocr_text"])
    else:
        print("No text detected.")

    if result["warnings"]:
        print("\n---------- WARNINGS ----------")
        for warning in result["warnings"]:
            print(f"- {warning}")

    print("\n-------------------------------------")
    print(f"Full OCR JSON saved to: {output_path}")
    print("Azure OCR test completed.")


if __name__ == "__main__":
    main()