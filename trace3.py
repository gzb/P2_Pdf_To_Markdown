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
            # 替换的情况，可能有多个字被替换为多个字
            # 我们把对应的 ds_text 中的空格先加上
            if i1 < i2:
                # 把第一个被替换字符前的空格加上
                catch_up_spaces(ds_pos_map[i1])
            # 插入替换的字符
            for k in range(j2 - j1):
                result.append(box_seq[j1 + k])
            # 把中间的空格保留？
            # 比如 DS 是 "a b c", Box 是 "x y z"
            # 替换 "a", "b", "c" -> "x", "y", "z"
            # 最好是按照 Box 的字符，中间如果 DS 有空格，我们尽量保留
            # 简单起见，替换段内的所有空格我们都保留在替换字符之后
            if i1 < i2:
                for k in range(i1, i2):
                    ds_idx = ds_pos_map[k]
                    # 我们只需要把 ds_idx 到 ds_idx+1 之间的空格(如果有的话) 拿出来
                    # 其实 catch_up_spaces(ds_pos_map[i2-1] + 1) 会把所有的中间空格都加上，但顺序可能在最后。
                    pass
                # 这种简单替换可能导致空格堆积在后面。更精细的做法是：
                # 均匀分配 j1..j2 的字符到 i1..i2 的骨架中
                pass
            
            # 精细替换逻辑
            # DS: i1 到 i2
            # Box: j1 到 j2
            ds_idx_start = ds_pos_map[i1] if i1 < len(ds_pos_map) else len(ds_text)
            ds_idx_end = ds_pos_map[i2-1] + 1 if i2 > 0 and i2 - 1 < len(ds_pos_map) else len(ds_text)
            
            # 我们在遇到 replace 时，怎么安排空格？
            # 我们可以遍历 ds_text[ds_idx_start : ds_idx_end]
            # 遇到非空格，如果 box 还有剩余，就替换。如果没剩余，就丢弃。
            # 遇到空格，就保留。
            # 如果遍历完了，box 还有剩余，全加上。
            
        elif tag == 'delete':
            # DS 多出来的字符，我们丢弃字符，但保留中间的空格
            pass
        elif tag == 'insert':
            # Box 多出来的字符，直接插入
            pass

