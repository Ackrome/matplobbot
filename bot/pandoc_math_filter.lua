-- pandoc_math_filter.lua
-- A Pandoc Lua filter to sanitize math environments, specifically for fixing
-- various matrix environments that contain '\hline', which is invalid syntax for them.

-- A mapping of matrix environments to their corresponding delimiters.
local matrix_delimiters = {
  pmatrix = {'\\left(', '\\right)'},
  bmatrix = {'\\left[', '\\right]'},
  Bmatrix = {'\\left\\{', '\\right\\}'},
  vmatrix = {'\\left|', '\\right|'},
  Vmatrix = {'\\left\\|', '\\right\\|'},
}

-- This function is the core of the filter. It's called for each 'Math' element
-- in the Pandoc Abstract Syntax Tree (AST).
function Math(el)
  -- el.text contains the raw LaTeX code of the math element.
  local math_text = el.text
  
  -- This function will be called for each matrix environment found.
  local function sanitize_matrix(content)
    -- The first part of the content is the environment name, e.g., "pmatrix".
    -- The rest is the actual matrix data.
    local env_name, matrix_content = content:match("^(%w+)%s*(.*)")
    
    -- Check if this is a matrix type we handle and if it contains \hline.
    if matrix_delimiters[env_name] and matrix_content:find('\\hline') then
      -- It's an unsupported matrix with \hline. We need to convert it to an 'array'.
      
      -- 1. Determine the number of columns.
      -- We find the line with the most alignment tabs ('&').
      local max_cols = 0
      -- We iterate over lines, splitting by the line break command '\\'.
      for line in matrix_content:gmatch("([^\\\\]+)") do
        -- Remove any \hline commands from the line before counting columns.
        local clean_line = line:gsub('%s*\\hline%s*', '')
        if #clean_line > 0 then
          -- The number of columns is the number of '&' characters plus one.
          local cols_in_line = 1 + select(2, clean_line:gsub('&', ''))
          if cols_in_line > max_cols then
            max_cols = cols_in_line
          end
        end
      end
      
      -- 2. Build the replacement string.
      local col_spec = string.rep('c', max_cols)
      local delimiters = matrix_delimiters[env_name]
      -- We reconstruct the matrix using the 'array' environment and wrap it
      -- with the correct delimiters for the original matrix type.
      return delimiters[1] .. '\\begin{array}{' .. col_spec .. '}' .. matrix_content .. '\\end{array}' .. delimiters[2]
    end
    -- If no replacement is needed, return nil to keep the original text.
    return nil
  end

  -- This pattern finds any \begin{...}...\end{...} block.
  -- The 'sanitize_matrix' function is then called on the content inside.
  math_text = string.gsub(math_text, '\\begin{(.-)}(.-)\\end{%1}', function(env_name, content)
    -- We pass the environment name and content to our sanitizer.
    return sanitize_matrix(env_name .. content) or ('\\begin{'..env_name..'}'..content..'\\end{'..env_name..'}')
  end)

  -- Update the element's text with the potentially modified LaTeX code.
  el.text = math_text
  -- Return the modified element to be placed back into the AST.
  return el
end