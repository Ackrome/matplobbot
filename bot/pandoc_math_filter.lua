-- pandoc_math_filter.lua
-- A Pandoc Lua filter to sanitize math environments, specifically for fixing
-- various matrix environments that contain '\hline', which is invalid syntax for them.
-- This is the definitive, robust version that handles multiple environments and edge cases.
 
-- A mapping of matrix environments to their corresponding delimiters.
local matrix_delimiters = {
  pmatrix = {'(', ')'},
  bmatrix = {'[', ']'},
  Bmatrix = {'\\{', '\\}'},
  vmatrix = {'|', '|'},
  Vmatrix = {'\\|', '\\|'},
  -- We also add environments that don't have delimiters but don't support \hline
  gathered = {'.', '.'} -- Using '.' as a placeholder for no delimiter
}
 
-- This function is the core of the filter. It's called for each 'Math' element
-- in the Pandoc Abstract Syntax Tree (AST).
function Math(el)
  local math_text = el.text

  -- This function will be called recursively to process nested environments.
  local function process_content(text)
    -- The pattern finds the outermost environment first.
    -- `[^%b{}]*` is used to avoid matching across nested blocks, making it more robust.
    return text:gsub('\\begin{([a-z*A-Z]+)}([^%b{}]*\\end{%1})', function(env_name, inner_block)
      -- The content is the inner_block without the final `\end{`.
      local content = inner_block:sub(1, inner_block:len() - #('\\end{'..env_name..'}'))
      
      -- Recursively process the content of the current environment.
      local processed_content = process_content(content)
      
      -- Now, check if THIS environment needs to be converted.
      if matrix_delimiters[env_name] and processed_content:find('\\hline') then
        -- It's an unsupported environment with \hline. We need to convert it to an 'array'.
        
        -- 1. Determine the number of columns.
        local max_cols = 0
        for line in (processed_content .. '\\'):gmatch('(.-)\\\\[\r\n]?') do
          local clean_line = line:gsub('%s*\\hline%s*', '')
          if clean_line:match('%S') then
            local cols_in_line = 1 + select(2, clean_line:gsub('&', ''))
            if cols_in_line > max_cols then
              max_cols = cols_in_line
            end
          end
        end
        if max_cols == 0 then max_cols = 1 end
        
        -- 2. Build the replacement string.
        local col_spec = string.rep('c', max_cols)
        local delimiters = matrix_delimiters[env_name]
        
        local new_block = '\\begin{array}{' .. col_spec .. '}' .. processed_content .. '\\end{array}'
        
        -- Add delimiters only if they are not placeholders.
        if delimiters[1] ~= '.' then
          new_block = '\\left' .. delimiters[1] .. new_block .. '\\right' .. delimiters[2]
        end
        
        return new_block
      end
      
      -- If no conversion is needed for this environment, reconstruct it with its processed content.
      return '\\begin{' .. env_name .. '}' .. processed_content .. '\\end{' .. env_name .. '}'
    end)
  end

  el.text = process_content(math_text)
  return el
end