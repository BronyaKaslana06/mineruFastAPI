import os
import json
import copy
import aiofiles
import concurrent.futures
from typing import List

from loguru import logger
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from magic_pdf.pipe.UNIPipe import UNIPipe
from magic_pdf.pipe.OCRPipe import OCRPipe
from magic_pdf.pipe.TXTPipe import TXTPipe
from magic_pdf.pipe.AbsPipe import AbsPipe
from initModelPipe.ModelPipe import ModelPipe
from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter
import magic_pdf.model as model_config

model_config.__use_inside_model__ = True

app = FastAPI()

ocr_model = None
txt_model = None

def init_model():
    from magic_pdf.model.doc_analyze_by_custom_model import ModelSingleton
    try:
        model_manager = ModelSingleton()
        global ocr_model, txt_model
        txt_model = model_manager.get_model(False, False)
        logger.info(f"txt_model init final")
        ocr_model = model_manager.get_model(True, False)
        logger.info(f"ocr_model init final")
        return 0
    except Exception as e:
        logger.exception(e)
        return -1

@app.on_event("startup")
async def startup_event():
    model_init = init_model()
    logger.info(f"model_init: {model_init}")

# 上传目录
UPLOAD_DIRECTORY = "uploads"
PDF_EXTRACT_DIRECTORY = "mineru"

# 确保上传目录存在
if not os.path.exists(UPLOAD_DIRECTORY):
    os.makedirs(UPLOAD_DIRECTORY)
if not os.path.exists(PDF_EXTRACT_DIRECTORY):
    os.makedirs(PDF_EXTRACT_DIRECTORY)


def json_md_dump(
        pipe,
        md_writer,
        pdf_name,
        content_list,
        md_content,
):
    orig_model_list = copy.deepcopy(pipe.model_list)
    md_writer.write(
        content=json.dumps(orig_model_list, ensure_ascii=False, indent=4),
        path=f"{pdf_name}_model.json"
    )

    md_writer.write(
        content=json.dumps(pipe.pdf_mid_data, ensure_ascii=False, indent=4),
        path=f"{pdf_name}_middle.json"
    )

    md_writer.write(
        content=json.dumps(content_list, ensure_ascii=False, indent=4),
        path=f"{pdf_name}_content_list.json"
    )

    md_writer.write(
        content=md_content,
        path=f"{pdf_name}.md"
    )

model_init = init_model()
logger.info(f"model_init: {model_init}")

def pdf_parse_main(
        pdf_path: str,
        parse_method: str = 'auto',
        model_json_path: str = None,
        is_json_md_dump: bool = True,
        output_dir: str = None
):
    try:
        pdf_name = os.path.basename(pdf_path).split(".")[0]
        pdf_path_parent = os.path.dirname(pdf_path)

        if output_dir:
            output_path = os.path.join(output_dir, pdf_name)
        else:
            output_path = os.path.join(pdf_path_parent, pdf_name)

        output_image_path = os.path.join(output_path, 'images')

        image_path_parent = os.path.basename(output_image_path)

        pdf_bytes = open(pdf_path, "rb").read()  # 读取 pdf 文件的二进制数据

        if model_json_path:
            model_json = json.loads(open(model_json_path, "r", encoding="utf-8").read())
        else:
            model_json = []

        image_writer, md_writer = DiskReaderWriter(output_image_path), DiskReaderWriter(output_path)

        # if parse_method == "auto":
        #     jso_useful_key = {"_pdf_type": "", "model_list": model_json}
            # pipe = UNIPipe(pdf_bytes, jso_useful_key, image_writer)
        # elif parse_method == "txt":
        #     pipe = TXTPipe(pdf_bytes, model_json, image_writer)
        # elif parse_method == "ocr":
        #     pipe = OCRPipe(pdf_bytes, model_json, image_writer)
        # else:
        #     logger.error("unknown parse method, only auto, ocr, txt allowed")
        #     return {"error": "unknown parse method"}
        
        global ocr_model, txt_model
        jso_useful_key = {"_pdf_type": "", "model_list": model_json}
        pipe = ModelPipe(pdf_bytes=pdf_bytes, jso_useful_key=jso_useful_key, image_writer=image_writer, ocr_model=ocr_model, txt_model=txt_model)

        pipe.pipe_classify()

        if not model_json:
            if model_config.__use_inside_model__:
                pipe.pipe_analyze()  # 解析
            else:
                logger.error("need model list input")
                return {"error": "need model list input"}

        pipe.pipe_parse()

        content_list = pipe.pipe_mk_uni_format(image_path_parent, drop_mode="none")
        md_content = pipe.pipe_mk_markdown(image_path_parent, drop_mode="none")

        if is_json_md_dump:
            json_md_dump(pipe, md_writer, pdf_name, content_list, md_content)

        return {"status": "success", "pdf_name": pdf_name}

    except Exception as e:
        logger.exception(e)
        return {"error": str(e)}

@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile):
    try:
    # 定义文件的存储路径
        file_location = os.path.join(UPLOAD_DIRECTORY, file.filename)

        # 使用异步上下文管理器保存文件
        async with aiofiles.open(file_location, 'wb') as out_file:
            contents = await file.read()  # 读取文件内容
            await out_file.write(contents)  # 将内容写入目标文件

        #pdf解析
        pdf_parse_main(pdf_path=file_location, output_dir=PDF_EXTRACT_DIRECTORY)
        return {"filename" : file.filename, "pdf_path": PDF_EXTRACT_DIRECTORY + "/" + file.filename.split('.')[0]}
    except Exception as e:
        return {"error": str(e)}

@app.post("/uploadfiles/")
async def upload_files(files: List[UploadFile] = File(...)):
    results = []

    def process_file(file: UploadFile):
        try:
            # 定义文件的存储路径
            file_location = os.path.join(UPLOAD_DIRECTORY, file.filename)

            # 使用异步上下文管理器保存文件
            with open(file_location, 'wb') as out_file:
                contents = file.file.read()  # 读取文件内容
                out_file.write(contents)  # 将内容写入目标文件

            # 调用 PDF 解析主函数
            result = pdf_parse_main(file_location, output_dir=PDF_EXTRACT_DIRECTORY)
            return {file.filename: result}
        except Exception as e:
            return {file.filename: {"error": str(e)}}

    # 使用线程池来并行处理文件
    max_workers = 2  # 最大线程数量
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_file, file) for file in files]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    return JSONResponse(content={"results": results})

@app.get("/test")
def read_root():
    return {"Hello": "World"}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
