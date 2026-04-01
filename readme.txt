请编写函数：

请添加函数，接收：

路径 
out_folder=c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-2-json

img_folder=c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-1-images

遍历img_folder目录下的文件，根据文件名称对应的从out_folder读取对应的json文件。

先读取"image_dims”节点中的w表示图片的宽度，h表示图片的高度。根据文件中的boxes里面的坐标信息，在图片上画上对应的矩形，红色。注意boxes中的坐标表示将w的值转为1024后的相对值。

将新文件存放到：
c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-1-images-ds-ocr目录下。

=======

请添加函数，接收参数：

路径 
ds_json_folder=c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-2-json

py_json_folder=c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-2-json-pyhton

遍历ds_json_folder目录下的文件(*.json)，根据文件名称对应的从py_json_folder读取相同文件名称的json文件。

读取ds_json_folder目录下的json文件中的"image_dims节点中的w表示图片的宽度，h表示图片的高度。
读取py_json_folder目录下的json文件中的"width"表示图片的宽度，"height"表示图片的高度。
将py_json_folder 目录下的json文件中的 "bbox" 的坐标，等比例转换成 image_dims中的坐标。

之后遍历：ds_json_folder目录下的json文件中"boxes"中的box的坐标区块，将box中的左上角的x,y的值减小5，右下角的x,y的值加大5。
根据新的box的坐标块从py_json_folder 目录下的json文件中的 "bbox" 的坐标区块在box的区块的“text”的内容从上到下的顺序链接到一起，写入到与box属性评级的节点中。

将新文件存放到：
c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-2-json-py-to-ds目录下。



====

请优化代码，在使用PyMuPDF读取pdf中的文字时候，例如文件中句子的脚注图标① 、② 等，会被读取成为了a、 b的文字，是否可以解决此类问题。（问题应该是出现在extract_pdf_to_json函数的代码中）


请完善代码：
在记录"merged_boxes"节点的信息时候，请在同级别的位置，记录合并的text_content的内容的长度信息。



======


2026.04.01

请重新梳理代码。

1. pdf-2-json目录存放的是通过deepseek-ocr模型识别出来的数据，坐标布局分析的区块比较好，但

有识别出来的错字。
2. pdf-2-json-python 目录存放的是pymupdf识别出来的数据局，文字数据准确。
3. pdf-2-json-py-to-ds 目录存放的是 结合pdf-2-json和pdf-2-json-python数据的优势的结果。
（目前目录里面的数据存在bug，需要进一步修改对应的代码：
a.如果pdf-2json的数据中存在table,目标文件中的text数据使用ocr的数据。
b.如果pdf-2-json-python区块没有内容但ocr的有内容，则使用ocr的
）

4.使用pdf-2-json-py-to-ds里面的数据 进行页面布局内容的合并存放到：pdf-2-json-py-to-ds-curpage-merged

5. 使用pdf-2-json-py-to-ds-curpage-merged里面的数据，进行跨页合并，并进行数组过渡嵌套的处理，将最终文件写入pdf-3-mk文件夹中。


====

请继续完善代码：
1. 如果pdf-2-json-python区块没有内容但ocr的有内容，则使用ocr的，是需要分析：ocr分析出来的json文件中的"raw_text"节点里面的数据，将此数据参照原来的代码
进行数据提取，将text放到boxs中对应的"text_content"节点里.