import difflib

def merge_text_v2(ds_text, box_text):
    ds_seq = []
    ds_pos_map = []
    for i, char in enumerate(ds_text):
        if not char.isspace():
            ds_seq.append(char)
            ds_pos_map.append(i)
            
    box_seq = [c for c in box_text if not c.isspace()]
    
    sm = difflib.SequenceMatcher(None, ds_seq, box_seq)
    
    result = []
    last_ds_idx = 0
    
    def catch_up_spaces(target_idx):
        nonlocal last_ds_idx
        while last_ds_idx < target_idx:
            if ds_text[last_ds_idx].isspace():
                result.append(ds_text[last_ds_idx])
            last_ds_idx += 1

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                ds_idx = ds_pos_map[i1 + k]
                catch_up_spaces(ds_idx)
                result.append(box_seq[j1 + k])
                last_ds_idx = ds_idx + 1
        elif tag == 'replace':
            if i1 < i2:
                catch_up_spaces(ds_pos_map[i1])
            
            box_idx = j1
            if i1 < i2:
                ds_idx_start = ds_pos_map[i1]
                ds_idx_end = ds_pos_map[i2 - 1] + 1
                
                for idx in range(ds_idx_start, ds_idx_end):
                    if ds_text[idx].isspace():
                        result.append(ds_text[idx])
                    else:
                        if box_idx < j2:
                            result.append(box_seq[box_idx])
                            box_idx += 1
                last_ds_idx = ds_idx_end
                
            while box_idx < j2:
                result.append(box_seq[box_idx])
                box_idx += 1
                
        elif tag == 'delete':
            if i1 < i2:
                ds_idx_start = ds_pos_map[i1]
                ds_idx_end = ds_pos_map[i2 - 1] + 1
                catch_up_spaces(ds_idx_start)
                for idx in range(ds_idx_start, ds_idx_end):
                    if ds_text[idx].isspace():
                        result.append(ds_text[idx])
                last_ds_idx = ds_idx_end
                
        elif tag == 'insert':
            if i1 < len(ds_pos_map):
                catch_up_spaces(ds_pos_map[i1])
            else:
                catch_up_spaces(len(ds_text))
            
            for k in range(j2 - j1):
                result.append(box_seq[j1 + k])

    catch_up_spaces(len(ds_text))
    return "".join(result)

if __name__ == "__main__":
    test_ds_text = r"坚持鼓励与规范并重，依法审理网络约车、快递服务、新型旅游、网络购物等“互联网 \(+\) ”新型消费纠纷。2022年3月，最高人民法院发布《最高人民法院关于审理网络消费纠纷案件适用法律若干问题的规定（一）》，对电子商务经营者提供的格式条款效力进行了界定，明确了电子商务平台经营者销售商品与提供服务的责任范围，细化了网络直播营销平台经营者以及网络餐饮服务平台经营者的侵权责任，加大了对消费者权益保护力度，促进网络经济健康发展，持续助力营造清朗网络空间。2023年3月，发布网络消费典型案例10件，涉及负面内"
    test_box_text = "坚持鼓励与规范并重，依法审理网络约车、快递服务、新型旅游、网络购物等“互联网＋”新型消费纠纷。2022 年3 月，最高人民法院发布《最高人民法院关于审理网络消费纠纷案件适用法律若干问题的规定（一）》，对电子商务经营者提供的格式条款效力进行了界定，明确了电子商务平台经营者销售商品与提供服务的责任范围，细化了网络直播营销平台经营者以及网络餐饮服务平台经营者的侵权责任，加大了对消费者权益保护力度，促进网络经济健康发展，持续助力营造清朗网络空间。2023 年3 月，发布网络消费典型案例10 件，涉及负面内"
    
    print(repr(merge_text_v2(test_ds_text, test_box_text)))
