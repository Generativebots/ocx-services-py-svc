-- Redis Lua Script: enforce_policy.lua
-- KEYS[1]: The Policy ID (e.g., "policy:FIN-001")
-- ARGV[1]: The Attribute Name to check (e.g., "amount")
-- ARGV[2]: The Value to test (e.g., "65.00")

local policy = redis.call('HMGET', KEYS[1], 'threshold', 'action_if_exceeded', 'logic_operator')
local threshold = tonumber(policy[1])
local action_on_violation = policy[2]
local operator = policy[3]
local input_value = tonumber(ARGV[2])

if not threshold then
    -- Fail Open or Closed? Usually Open if policy missing, but for security maybe "FLAG"
    return "POLICY_NOT_FOUND" 
end

-- Evaluation Logic
if operator == ">" then
    if input_value > threshold then
        return action_on_violation
    end
elseif operator == "<" then
    if input_value < threshold then
        return action_on_violation
    end
end

return "ALLOW"
