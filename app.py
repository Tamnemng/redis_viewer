from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import redis
import json

app = Flask(__name__)
app.secret_key = 'thisisasecretkey'  # Cần thiết cho flash messages

# Kết nối Redis
r = redis.StrictRedis(host="192.168.100.14", port=16379, password="ThInK4!*!!", decode_responses=True)

@app.route("/")
def index():
    search_key = request.args.get('key', '')
    pattern_search = request.args.get('pattern', '')
    
    if search_key:
        # Nếu có key cụ thể, chỉ lấy key đó
        keys = [search_key] if r.exists(search_key) else []
    elif pattern_search:
        # Tìm kiếm theo pattern cụ thể
        keys = r.keys(f"*{pattern_search}*")
    else:
        # Ngược lại lấy tất cả các key có pattern "myapp||*"
        keys = r.keys("myapp||*")
    
    data = {}

    for key in keys:
        # Check the type of the Redis key
        key_type = r.type(key)
        
        if key_type == "string":
            try:
                value = r.get(key)
                parsed_value = json.loads(value) if value else value
                data[key] = parsed_value if isinstance(parsed_value, dict) else {"value": parsed_value}
                if isinstance(parsed_value, dict):
                    data[key]["type"] = "string (JSON)"
                elif isinstance(parsed_value, list):
                    data[key] = {"value": parsed_value, "type": "string (Array)"}
                else:
                    data[key]["type"] = "string"
            except json.JSONDecodeError:
                data[key] = {"value": value, "type": "string"}
        
        elif key_type == "hash":
            hash_data = r.hgetall(key)
            data[key] = hash_data
            data[key]["type"] = "hash"
        
        elif key_type == "list":
            list_data = r.lrange(key, 0, -1)
            data[key] = {"values": list_data, "type": "list"}
        
        elif key_type == "set":
            set_data = r.smembers(key)
            data[key] = {"values": list(set_data), "type": "set"}
        
        elif key_type == "zset":
            zset_data = r.zrange(key, 0, -1, withscores=True)
            data[key] = {"values": dict(zset_data), "type": "zset"}
        
        else:
            data[key] = {"value": "Unsupported type", "type": key_type}

    # Get unique patterns from all keys for filter dropdown
    all_keys = r.keys("*")
    patterns = set()
    for key in all_keys:
        parts = key.split(":")
        if len(parts) > 0:
            patterns.add(parts[0])

    return render_template("index.html", data=data, patterns=patterns, current_pattern=pattern_search)

@app.route("/view/<path:key>")
def view_key(key):
    if not r.exists(key):
        flash("Key không tồn tại!", "danger")
        return redirect(url_for('index'))
    
    key_type = r.type(key)
    key_data = {}
    
    if key_type == "string":
        try:
            value = r.get(key)
            parsed_value = json.loads(value) if value else value
            if isinstance(parsed_value, dict):
                key_data = {"value": parsed_value, "type": "string (JSON)"}
            elif isinstance(parsed_value, list):
                key_data = {"value": parsed_value, "type": "string (Array)"}
            else:
                key_data = {"value": parsed_value, "type": "string"}
        except json.JSONDecodeError:
            key_data = {"value": value, "type": "string"}
    
    elif key_type == "hash":
        key_data = {"value": r.hgetall(key), "type": "hash"}
    
    elif key_type == "list":
        key_data = {"value": r.lrange(key, 0, -1), "type": "list"}
    
    elif key_type == "set":
        key_data = {"value": list(r.smembers(key)), "type": "set"}
    
    elif key_type == "zset":
        key_data = {"value": dict(r.zrange(key, 0, -1, withscores=True)), "type": "zset"}
    
    else:
        key_data = {"value": "Unsupported type", "type": key_type}
    
    return render_template("view_key.html", key=key, data=key_data)

@app.route("/delete/<path:key>", methods=["POST"])
def delete_key(key):
    if r.exists(key):
        r.delete(key)
        flash(f"Key '{key}' đã được xóa thành công!", "success")
    else:
        flash(f"Key '{key}' không tồn tại!", "danger")
    
    return redirect(url_for('index'))

@app.route("/delete_item/<path:key>", methods=["POST"])
def delete_item(key):
    item_index = request.form.get('index')
    item_value = request.form.get('value')
    
    if not r.exists(key):
        flash(f"Key '{key}' không tồn tại!", "danger")
        return redirect(url_for('index'))
    
    key_type = r.type(key)
    
    if key_type == "string":
        try:
            value = r.get(key)
            data = json.loads(value)
            
            if isinstance(data, list) and item_index is not None:
                try:
                    index = int(item_index)
                    if 0 <= index < len(data):
                        data.pop(index)
                        r.set(key, json.dumps(data))
                        flash(f"Đã xóa item tại vị trí {index}", "success")
                    else:
                        flash(f"Index {index} nằm ngoài phạm vi mảng!", "danger")
                except ValueError:
                    flash("Index phải là số nguyên!", "danger")
            else:
                flash("Dữ liệu không phải là mảng hoặc không có index được cung cấp!", "danger")
                
        except json.JSONDecodeError:
            flash("Dữ liệu không phải là JSON hợp lệ!", "danger")
    
    elif key_type == "list":
        if item_value:
            count = r.lrem(key, 1, item_value)
            if count > 0:
                flash(f"Đã xóa 1 item có giá trị '{item_value}'", "success")
            else:
                flash(f"Không tìm thấy item có giá trị '{item_value}'", "warning")
                
    elif key_type == "set":
        if item_value:
            result = r.srem(key, item_value)
            if result > 0:
                flash(f"Đã xóa item '{item_value}' khỏi set", "success")
            else:
                flash(f"Item '{item_value}' không tồn tại trong set", "warning")
    
    elif key_type == "hash":
        field = request.form.get('field')
        if field:
            result = r.hdel(key, field)
            if result > 0:
                flash(f"Đã xóa field '{field}' khỏi hash", "success")
            else:
                flash(f"Field '{field}' không tồn tại trong hash", "warning")
                
    elif key_type == "zset":
        if item_value:
            result = r.zrem(key, item_value)
            if result > 0:
                flash(f"Đã xóa member '{item_value}' khỏi sorted set", "success")
            else:
                flash(f"Member '{item_value}' không tồn tại trong sorted set", "warning")
    
    return redirect(url_for('view_key', key=key))

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)