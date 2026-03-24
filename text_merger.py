import re

def merge_text(deepseek_ocr_text: str, box_text: str) -> str:
    """
    合并 DeepSeek OCR 识别的文本与 PyMuPDF 提取的文本（box_text）。
    
    规则：
    1. deepseek_ocr_text 提供了正确的控制符号（如空格、回车、换行等），但可能有错别字。
    2. box_text 提供了正确的文本内容，但控制符号（排版）可能混乱或不正确。
    3. 将 box_text 中的真实字符按顺序“填入” deepseek_ocr_text 的排版骨架中。
    
    :param deepseek_ocr_text: 包含正确排版但可能有错别字的字符串
    :param box_text: 包含正确文字但排版可能有误的字符串
    :return: 合并后的字符串
    """
    
    # 提取 box_text 中所有非空白字符，作为“正确字符”的来源队列
    # 使用 \s 匹配所有空白字符（包括空格、\n、\r、\t 等），并将其过滤掉
    box_chars = [char for char in box_text if not char.isspace()]
    box_len = len(box_chars)
    box_idx = 0
    
    result = []
    
    # 遍历带有正确控制符号的 deepseek_ocr_text
    for char in deepseek_ocr_text:
        if char.isspace():
            # 如果是空白/控制符号（空格、换行等），直接保留 DeepSeek 的格式
            result.append(char)
        else:
            # 如果是实际可见字符，则从 box_text 提取正确的字符进行替换
            if box_idx < box_len:
                result.append(box_chars[box_idx])
                box_idx += 1
            else:
                # 如果 box_text 的字符已经用完，但 deepseek 还有多余字符，则保留 deepseek 原字符（兜底容错）
                result.append(char)
                
    # 如果 deepseek_ocr_text 遍历完后，box_text 还有剩余未填入的字符，则将其追加到末尾
    if box_idx < box_len:
        result.append("".join(box_chars[box_idx:]))
        
    return "".join(result)

if __name__ == "__main__":
    # 测试用例
    test_ds_text = "坚持鼓励与规范并重，依法审理网络约车、快递服务、新型旅游、网络购物等“互联网 \\(+\\) ”新型消费纠纷。2022年3月，最高人民法院发布《最高人民法院关于审理网络消费纠纷案件适用法律若干问题的规定（一）》，对电子商务经营者提供的格式条款效力进行了界定，明确了电子商务平台经营者销售商品与提供服务的责任范围，细化了网络直播营销平台经营者以及网络餐饮服务平台经营者的侵权责任，加大了对消费者权益保护力度，促进网络经济健康发展，持续助力营造清朗网络空间。2023年3月，发布网络消费典型案例10件，涉及负面内"
    test_box_text = "坚持鼓励与规范并重，依法审理网络约车、快递服务、新型旅游、网络购物等“互联网＋”新型消费纠纷。2022 年3 月，最高人民法院发布《最高人民法院关于审理网络消费纠纷案件适用法律若干问题的规定（一）》，对电子商务经营者提供的格式条款效力进行了界定，明确了电子商务平台经营者销售商品与提供服务的责任范围，细化了网络直播营销平台经营者以及网络餐饮服务平台经营者的侵权责任，加大了对消费者权益保护力度，促进网络经济健康发展，持续助力营造清朗网络空间。2023 年3 月，发布网络消费典型案例10 件，涉及负面内"
    
    print("--- 测试结果 ---")
    print("DeepSeek 原文本 (排版对，字错):")
    print(repr(test_ds_text))
    print("\nBox 原文本 (字对，排版错):")
    print(repr(test_box_text))
    
    merged = merge_text(test_ds_text, test_box_text)
    
    print("\n合并后文本:")
    print(repr(merged))
    # 预期输出应为: '这 是一个\n测试。无 错别字！'
