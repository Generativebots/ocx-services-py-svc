-- Redis Lua Script: JSON-Logic Enforcement
-- Supports full JSON-Logic standard: and, or, not, in, >, <, >=, <=, ==, !=, var
-- KEYS[1]: The Policy ID (e.g., "policy:PURCHASE_AUTH_001")
-- ARGV[1]: The JSON-encoded data payload
-- ARGV[2]: The JSON-encoded context (whitelist, pre-approved lists, etc.)

-- Helper: Parse JSON
local function parse_json(str)
    local cjson = require("cjson")
    return cjson.decode(str)
end

-- Helper: Get nested value from table using dot notation
local function get_var(data, path)
    if type(path) ~= "string" then
        return nil
    end
    
    local keys = {}
    for key in string.gmatch(path, "[^.]+") do
        table.insert(keys, key)
    end
    
    local value = data
    for _, key in ipairs(keys) do
        if type(value) ~= "table" then
            return nil
        end
        value = value[key]
    end
    
    return value
end

-- Helper: Check if value is in list
local function is_in(value, list)
    if type(list) ~= "table" then
        return false
    end
    
    for _, item in ipairs(list) do
        if item == value then
            return true
        end
    end
    
    return false
end

-- Main evaluation function
local function evaluate_logic(logic, data)
    if type(logic) ~= "table" then
        return logic
    end
    
    -- Variable substitution
    if logic["var"] then
        return get_var(data, logic["var"])
    end
    
    -- Comparison operators
    if logic[">"] then
        local args = logic[">"]
        local left = evaluate_logic(args[1], data)
        local right = evaluate_logic(args[2], data)
        return tonumber(left) > tonumber(right)
    end
    
    if logic["<"] then
        local args = logic["<"]
        local left = evaluate_logic(args[1], data)
        local right = evaluate_logic(args[2], data)
        return tonumber(left) < tonumber(right)
    end
    
    if logic[">="] then
        local args = logic[">="]
        local left = evaluate_logic(args[1], data)
        local right = evaluate_logic(args[2], data)
        return tonumber(left) >= tonumber(right)
    end
    
    if logic["<="] then
        local args = logic["<="]
        local left = evaluate_logic(args[1], data)
        local right = evaluate_logic(args[2], data)
        return tonumber(left) <= tonumber(right)
    end
    
    if logic["=="] then
        local args = logic["=="]
        local left = evaluate_logic(args[1], data)
        local right = evaluate_logic(args[2], data)
        return left == right
    end
    
    if logic["!="] then
        local args = logic["!="]
        local left = evaluate_logic(args[1], data)
        local right = evaluate_logic(args[2], data)
        return left ~= right
    end
    
    -- Boolean operators
    if logic["and"] then
        for _, condition in ipairs(logic["and"]) do
            if not evaluate_logic(condition, data) then
                return false
            end
        end
        return true
    end
    
    if logic["or"] then
        for _, condition in ipairs(logic["or"]) do
            if evaluate_logic(condition, data) then
                return true
            end
        end
        return false
    end
    
    if logic["not"] then
        return not evaluate_logic(logic["not"], data)
    end
    
    -- Membership operator
    if logic["in"] then
        local args = logic["in"]
        local value = evaluate_logic(args[1], data)
        local list = evaluate_logic(args[2], data)
        return is_in(value, list)
    end
    
    -- Default: return as-is
    return logic
end

-- Main execution
local policy_data = redis.call('HMGET', KEYS[1], 'logic', 'action', 'tier')
local logic_json = policy_data[1]
local action_json = policy_data[2]
local tier = policy_data[3]

if not logic_json then
    return cjson.encode({
        result = "POLICY_NOT_FOUND",
        policy_id = KEYS[1],
        error = "Policy does not exist in Redis"
    })
end

-- Parse inputs
local data = parse_json(ARGV[1])
local context = parse_json(ARGV[2] or "{}")

-- Merge context into data
for k, v in pairs(context) do
    data[k] = v
end

-- Parse and evaluate logic
local logic = parse_json(logic_json)
local action = parse_json(action_json)

local violates = evaluate_logic(logic, data)

-- Return result
if violates then
    return cjson.encode({
        result = action["on_fail"] or "BLOCK",
        policy_id = KEYS[1],
        tier = tier,
        violated = true,
        required_signals = action["required_signals"]
    })
else
    return cjson.encode({
        result = action["on_pass"] or "ALLOW",
        policy_id = KEYS[1],
        tier = tier,
        violated = false
    })
end
