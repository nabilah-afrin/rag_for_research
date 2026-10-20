from pathlib import Path
from docling_core.types.doc import ImageRefMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions


def convert_pdf_folder(input_folder: str, output_folder: str):
    input_path = Path(input_folder)
    output_path = Path(output_folder)

    if not input_path.exists():
        raise FileNotFoundError(f"Input folder not found: {input_path}")

    if not input_path.is_dir():
        raise ValueError(f"Input path is not a folder: {input_path}")

    output_path.mkdir(parents=True, exist_ok=True)

    # Configure Docling
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.do_formula_enrichment = True
    pipeline_options.do_code_enrichment = True
    pipeline_options.images_scale = 2.0
    pipeline_options.generate_picture_images = True

    # Create converter once and reuse it for all PDFs
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options
            )
        }
    )

    # Find all PDFs in the input folder
    pdf_files = list(input_path.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in: {input_path}")
        return

    print(f"Found {len(pdf_files)} PDF file(s).")

    for pdf_file in pdf_files:
        print(f"\nProcessing: {pdf_file.name}")

        try:
            # Convert PDF
            result = converter.convert(str(pdf_file))
            doc = result.document

            # -------------------------------------------------
            # Extract text
            # -------------------------------------------------
            markdown_text = doc.export_to_markdown()

            character_count = len(markdown_text)
            page_count = len(doc.pages)
            # Output markdown file
            output_file = output_path / f"{pdf_file.stem}.md"

            # # Save markdown + referenced images
            # doc.save_as_markdown(
            #     output_file,
            #     image_mode=ImageRefMode.REFERENCED
            # )

            print(f"✓ Converted: {pdf_file.name}")
            document_metadata.append({
                "filename": pdf_file.name,
                "characters": character_count,
                "pages": page_count,
                "characters_per_page": (
                    character_count / page_count
                    if page_count > 0 else 0
                )
            })
            total_characters += character_count
            total_pages += page_count

        except Exception as e:
            print(f"✗ Failed: {pdf_file.name}")
            print(f"  Error: {e}")


    number_of_documents = len(document_metadata)

    if number_of_documents > 0:

        average_characters_per_document = (
            total_characters / number_of_documents
        )

        smallest_document = min(
            document_metadata,
            key=lambda x: x["characters"]
        )

        largest_document = max(
            document_metadata,
            key=lambda x: x["characters"]
        )

    else:

        average_characters_per_document = 0
        smallest_document = None
        largest_document = None

    # ---------------------------------------------------------
    # Final metadata
    # ---------------------------------------------------------

    metadata = {
        "dataset_statistics": {
            "number_of_documents": number_of_documents,
            "total_extracted_characters": total_characters,
            "total_pages": total_pages,
            "average_characters_per_document": (
                round(average_characters_per_document, 2)
            ),
            "smallest_document": smallest_document,
            "largest_document": largest_document
        },

        "documents": document_metadata
    }

    # ---------------------------------------------------------
    # Save JSON
    # ---------------------------------------------------------

    metadata_file = output_path / "rag_metadata.json"

    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(
            metadata,
            f,
            indent=4,
            ensure_ascii=False
        )
    print("\nDone.")

convert_pdf_folder('/content/pdf_input','/content/markdown_output' )
