import difflib

def merge_text(deepseek_ocr_text: str, box_text: str) -> str:
    """
    合并 DeepSeek OCR 识别的文本与 PyMuPDF 提取的文本（box_text）。
    
    规则：
    1. deepseek_ocr_text 提供了正确的控制符号（如空格、回车、换行等），但可能有错别字（或多字、少字）。
    2. box_text 提供了正确的文本内容，但控制符号（排版）可能混乱或不正确。
    3. 使用 difflib 进行序列对齐，将 box_text 中的真实字符“智能填入” deepseek_ocr_text 的排版骨架中，避免因字数不一致导致的错位。
    
    :param deepseek_ocr_text: 包含正确排版但可能有错别字的字符串
    :param box_text: 包含正确文字但排版可能有误的字符串
    :return: 合并后的字符串
    """
    
    # 提取非空字符并记录其在 deepseek_ocr_text 中的原始索引
    ds_seq = []
    ds_pos_map = []
    for i, char in enumerate(deepseek_ocr_text):
        if not char.isspace():
            ds_seq.append(char)
            ds_pos_map.append(i)
            
    # 提取 box_text 中的非空字符序列
    box_seq = [char for char in box_text if not char.isspace()]
    
    # 使用 difflib 寻找最长公共子序列（对齐两个纯字符序列）
    sm = difflib.SequenceMatcher(None, ds_seq, box_seq)
    
    result = []
    last_ds_idx = 0
    
    # 辅助函数：将 deepseek_ocr_text 中被跳过的控制符号（空格、换行）补齐
    def catch_up_spaces(target_idx):
        nonlocal last_ds_idx
        while last_ds_idx < target_idx:
            if deepseek_ocr_text[last_ds_idx].isspace():
                result.append(deepseek_ocr_text[last_ds_idx])
            last_ds_idx += 1

    # 根据对齐结果进行合并
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            # 完全匹配，填入 box 的字符，并保留对应位置的空格
            for k in range(i2 - i1):
                ds_idx = ds_pos_map[i1 + k]
                catch_up_spaces(ds_idx)
                result.append(box_seq[j1 + k])
                last_ds_idx = ds_idx + 1
                
        elif tag == 'replace':
            # 替换：可能字符数不同。先补齐第一个字符前的空格
            if i1 < i2:
                catch_up_spaces(ds_pos_map[i1])
            
            box_idx = j1
            if i1 < i2:
                ds_idx_start = ds_pos_map[i1]
                ds_idx_end = ds_pos_map[i2 - 1] + 1
                
                # 遍历 ds 这段区间，遇到可见字符就尝试用 box 字符替换，遇到空格则保留
                for idx in range(ds_idx_start, ds_idx_end):
                    if deepseek_ocr_text[idx].isspace():
                        result.append(deepseek_ocr_text[idx])
                    else:
                        if box_idx < j2:
                            result.append(box_seq[box_idx])
                            box_idx += 1
                last_ds_idx = ds_idx_end
                
            # 如果 ds 的槽位用完了，box 还有多余的替换字符，直接追加
            while box_idx < j2:
                result.append(box_seq[box_idx])
                box_idx += 1
                
        elif tag == 'delete':
            # 删除：ds 中多余的字符（例如 OCR 幻觉产生的多余字符）。
            # 不输出字符，但要保留这段区间内的空格
            if i1 < i2:
                ds_idx_start = ds_pos_map[i1]
                ds_idx_end = ds_pos_map[i2 - 1] + 1
                catch_up_spaces(ds_idx_start)
                for idx in range(ds_idx_start, ds_idx_end):
                    if deepseek_ocr_text[idx].isspace():
                        result.append(deepseek_ocr_text[idx])
                last_ds_idx = ds_idx_end
                
        elif tag == 'insert':
            # 插入：box 中多出来的字符。
            # 直接在当前位置插入，先补齐到当前位置的空格
            if i1 < len(ds_pos_map):
                catch_up_spaces(ds_pos_map[i1])
            else:
                catch_up_spaces(len(deepseek_ocr_text))
            
            for k in range(j2 - j1):
                result.append(box_seq[j1 + k])

    # 补齐末尾可能剩余的控制符号
    catch_up_spaces(len(deepseek_ocr_text))
    
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
