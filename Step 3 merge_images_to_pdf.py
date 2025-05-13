import sys
import io
from PyQt5.QtWidgets import (QApplication, QFileDialog, QMessageBox,
                             QInputDialog, QLineEdit)
from PIL import Image
import pytesseract
from pypdf import PdfWriter, PdfReader

def select_images_and_merge_to_pdf():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    files, _ = QFileDialog.getOpenFileNames(
        None,
        "Select images to merge into PDF",
        "",
        "Image Files (*.png *.jpg *.jpeg *.bmp *.tiff *.tif)"
    )
    if not files:
        QMessageBox.information(None, "No Files", "No image files were selected.")
        return

    output_pdf, _ = QFileDialog.getSaveFileName(
        None,
        "Save merged PDF as...",
        "",
        "PDF Files (*.pdf)"
    )
    if not output_pdf:
        QMessageBox.information(None, "No Output File", "No output PDF file path was selected.")
        return

    pil_images = []
    valid_files = []
    for file_path in files:
        try:
            img = Image.open(file_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            pil_images.append(img)
            valid_files.append(file_path)
        except Exception as e:
            QMessageBox.warning(None, "Image Load Error", f"Could not load image {file_path}: {e}\nSkipping this file.")
    
    if not pil_images:
        QMessageBox.warning(None, "No Valid Images", "No valid images could be loaded.")
        return
    
    files = valid_files 

    reply = QMessageBox.question(None, 'OCR Option',
                                 "Do you want to perform OCR to make the PDF searchable?\n"
                                 "(Requires Tesseract OCR installed and in PATH).\n"
                                 "If OCR fails for an image, it will be added as image-only.",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

    perform_ocr = (reply == QMessageBox.Yes)
    ocr_lang = 'eng'
    ocr_dpi = 300

    if perform_ocr:
        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError:
            QMessageBox.critical(None, "Tesseract Not Found",
                                 "Tesseract OCR is not installed or not found in your system's PATH.\n"
                                 "The PDF will be created as image-only.")
            perform_ocr = False
        except Exception as e:
            QMessageBox.warning(None, "Tesseract Check Error",
                                f"Could not verify Tesseract version: {e}\n"
                                "Proceeding with OCR, but it might fail.")

        if perform_ocr:
            lang_input, ok = QInputDialog.getText(None, "OCR Language",
                                                  "Enter language code(s) for OCR (e.g., 'eng', 'deu', 'eng+fra'):",
                                                  QLineEdit.Normal, ocr_lang)
            if ok and lang_input and lang_input.strip():
                ocr_lang = lang_input.strip()
            elif ok and not (lang_input and lang_input.strip()):
                 QMessageBox.warning(None, "OCR Language", "Empty language entered. Using default: 'eng'.")
                 ocr_lang = 'eng'
            elif not ok :
                 QMessageBox.warning(None, "OCR Language", "Language input cancelled. Using default: 'eng'.")
                 ocr_lang = 'eng'

            dpi_input, ok = QInputDialog.getInt(None, "OCR DPI",
                                                "Enter DPI for OCR processing (e.g., 300):",
                                                ocr_dpi, 70, 1200, 10)
            if ok:
                ocr_dpi = dpi_input
            else:
                 QMessageBox.warning(None, "OCR DPI", f"DPI input cancelled. Using default: {ocr_dpi}.")

    if perform_ocr:
        pdf_writer = PdfWriter()
        successful_ocr_count = 0
        processed_images_count = 0

        for idx, file_path in enumerate(files):
            try:
                QApplication.processEvents()
                print(f"Performing OCR on {file_path} (Lang: {ocr_lang}, DPI: {ocr_dpi})...")
                
                config_str = f"--dpi {ocr_dpi} -c tessedit_pageseg_mode=3"
                
                pdf_bytes = pytesseract.image_to_pdf_or_hocr(pil_images[idx], lang=ocr_lang, extension='pdf', config=config_str)
                
                if not pdf_bytes: 
                    raise pytesseract.TesseractError("OCR process returned empty PDF data.")

                pdf_reader_single = PdfReader(io.BytesIO(pdf_bytes))
                for page in pdf_reader_single.pages: 
                    pdf_writer.add_page(page)
                successful_ocr_count += 1
                processed_images_count +=1
                print(f"Successfully OCR'd and added {file_path}.")

            except pytesseract.TesseractError as e_ocr:
                msg = f"OCR failed for image: {file_path}\nError: {e_ocr}\n\nThis image will be added as image-only to the PDF."
                QMessageBox.warning(None, "OCR Error", msg)
                print(msg)
                pil_image_to_add = pil_images[idx]
                img_byte_arr = io.BytesIO()
                pil_image_to_add.save(img_byte_arr, format='PDF', resolution=float(ocr_dpi)) 
                img_byte_arr.seek(0)
                pdf_reader_fallback = PdfReader(img_byte_arr)
                for page in pdf_reader_fallback.pages:
                    pdf_writer.add_page(page)
                processed_images_count +=1

            except Exception as e_generic:
                msg = f"An unexpected error occurred processing image: {file_path}\nError: {e_generic}\n\nThis image will be added as image-only."
                QMessageBox.critical(None, "Unexpected Processing Error", msg)
                print(msg)
                pil_image_to_add = pil_images[idx]
                img_byte_arr = io.BytesIO()
                pil_image_to_add.save(img_byte_arr, format='PDF', resolution=float(ocr_dpi))
                img_byte_arr.seek(0)
                pdf_reader_fallback = PdfReader(img_byte_arr)
                for page in pdf_reader_fallback.pages:
                    pdf_writer.add_page(page)
                processed_images_count +=1
        
        if not pdf_writer.pages: 
             QMessageBox.information(None, "PDF Creation Failed", "No pages were successfully processed. PDF not saved.")
             return

        with open(output_pdf, "wb") as f_out:
            pdf_writer.write(f_out)
        
        summary_message = f"PDF saved as: {output_pdf}\n"
        summary_message += f"{processed_images_count}/{len(files)} images processed.\n"
        if successful_ocr_count == processed_images_count and processed_images_count > 0:
            summary_message += "All processed images were made searchable."
        elif successful_ocr_count > 0:
            summary_message += f"{successful_ocr_count} images were made searchable. Others were added as image-only due to OCR issues."
        elif processed_images_count > 0 : 
             summary_message += "All processed images were added as image-only as OCR failed or was skipped for them."
        else: 
            summary_message = "PDF could not be created as no images were processed."

        QMessageBox.information(None, "PDF Saved", summary_message)

    else:  
        if not pil_images: 
            QMessageBox.warning(None, "No Images", "No valid images available to save.")
            return
            
        try:
            pil_images[0].save(output_pdf, save_all=True, append_images=pil_images[1:], resolution=100.0) 
            QMessageBox.information(None, "PDF Saved", f"Image-only PDF saved as: {output_pdf}")
        except Exception as e:
            QMessageBox.critical(None, "PDF Save Error", f"Could not save image-only PDF: {e}")


if __name__ == "__main__":
    select_images_and_merge_to_pdf()
    app = QApplication.instance()
    if app: 
        # In some environments, you might need sys.exit(app.exec_()) for a clean exit.
        # Depending on how the script is run, it might close automatically.
        pass