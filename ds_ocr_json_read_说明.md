# 数据结构重构与内容回填工具说明 (ds_ocr_json_read.py)

本工具用于将外部系统（如 OCR 引擎）生成的结构化数据与 PyMuPDF 生成的精准文本数据进行合并。它利用外部提供的“段落/区域”逻辑结构，结合内部提取的高精度文本，生成一份既具备逻辑结构又包含准确文本的终极数据文件。

## 核心功能

1.  **双源数据读取**:
    *   **主输入 (`*_processed_data.json`)**: 提供逻辑结构（段落、页面归属、区域坐标）。
    *   **辅助输入 (`*_mapping.json`)**: 提供精准的文本内容及其在 PDF 中的原始坐标。

2.  **坐标系统一**:
    *   自动识别主输入文件的页面原始尺寸 (`image_dims`)。
    *   将主输入中归一化（Width=1024）的坐标系，动态还原为 PDF 的原始坐标系，确保与辅助输入文件的坐标一致。

3.  **智能文本回填**:
    *   遍历主输入中的每一个逻辑块（Item）。
    *   对于每个逻辑块中的每一个坐标区域（Box），在辅助输入文件中查找空间重叠的文本。
    *   **排序与拼接**: 查找到的文本块严格按照“先上后下，先左后右”的顺序拼接，确保阅读顺序正确。
    *   **结构保持**: 严格保留主输入文件中的 `pages` 和 `boxs` 数组结构，`texts` 字段与之进行一对一的更新，不进行额外的数组合并。

4.  **结果输出**:
    *   **JSON**: 生成 `*_processed_data_new.json`，结构与原文件一致，但内容已更新。
    *   **Markdown**: 
        *   `*_original.md`: 转换前的原始内容预览。
        *   `*_new.md`: 转换后的新内容预览。

## 使用方法

### 命令行运行

```bash
python ds_ocr_json_read.py <processed_data_json_path>
```

### 示例

```bash
python ds_ocr_json_read.py "C:\gzb_file_to_github\P2_Pdf_To_Markdown\test_pdf\1_processed_data.json"
```

该命令会自动寻找同目录下的 `1_mapping.json`，处理后生成：
*   `1_processed_data_new.json`
*   `1_processed_data_new_original.md`
*   `1_processed_data_new_new.md`

## 关键逻辑细节

*   **坐标转换公式**: `x_real = x_norm * (original_width / 1024.0)`
*   **空间匹配算法**: 采用“中心点包含”或“区域重叠”判定，容忍一定的坐标误差。
*   **空数据处理**: 如果主输入中某条目为空，程序会跳过并保留原样，不会报错。
