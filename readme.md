# PDF_Extract网络接口

需要额外安装的包：

```shell
pip install aiofiles fastapi
```

启动服务器：

```shell
uvicorn main:app --reload
```

服务器启动在8000端口，pdf文件处理请求url如下，请求体body类型为form-data，有一参数类型为file，即为需要处理的文件。

```shell
http://127.0.0.1:8000/mineru/
```

处理完成后返回格式为，返回文件名和处理完成后的文件在服务器上的路径：

```json
{
    "filename": "small_ocr.pdf",
    "pdf_path": "mineru/small_ocr"
}
```



