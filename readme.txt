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