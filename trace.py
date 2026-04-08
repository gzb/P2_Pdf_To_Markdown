def trace():
    test_ds_text = "等“互联网 \(+\) ”新型消费纠纷。2022"
    test_box_text = "等“互联网＋”新型消费纠纷。2022"
    
    box_chars = [char for char in test_box_text if not char.isspace()]
    box_len = len(box_chars)
    box_idx = 0
    
    result = []
    
    for char in test_ds_text:
        if char.isspace():
            result.append(f"[{char}]")
        else:
            if box_idx < box_len:
                result.append(f"({char}->{box_chars[box_idx]})")
                box_idx += 1
            else:
                result.append(f"({char}->NONE)")
    print("".join(result))

trace()
