-- pandoc_math_filter.lua
-- A Pandoc Lua filter to sanitize math environments, specifically for fixing
-- various matrix environments that contain '\hline', which is invalid syntax for them.
-- This is a more robust version that handles nested environments correctly.
 
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
 
  -- This function will be called for each specific matrix environment found.
  local function sanitize_matrix(env_name, matrix_content)
    -- We only intervene if the content of the matrix contains '\hline'.
    if matrix_content:find('\\hline') then
      -- It's an unsupported matrix with \hline. We need to convert it to an 'array'.
 
      -- 1. Determine the number of columns.
      -- We find the line with the most alignment tabs ('&').
      local max_cols = 0
      -- We iterate over lines, splitting by the line break command '\\'.
      -- The pattern `.-(\\)` is non-greedy and captures content up to the next `\\`.
      for line in (matrix_content .. '\\'):gmatch('(.-)\\\\[\r\n]?') do
        -- Remove any \hline commands from the line before counting columns.
        local clean_line = line:gsub('%s*\\hline%s*', '')
        if clean_line:match('%S') then -- Check if the line contains non-whitespace characters
          -- The number of columns is the number of '&' characters plus one.
          local cols_in_line = 1 + select(2, clean_line:gsub('&', ''))
          if cols_in_line > max_cols then
            max_cols = cols_in_line
          end
        end
      end
 
      -- 2. Build the replacement string.
      if max_cols == 0 then max_cols = 1 end -- Fallback for empty matrices
      local col_spec = string.rep('c', max_cols)
      local delimiters = matrix_delimiters[env_name]
      -- We reconstruct the matrix using the 'array' environment and wrap it
      -- with the correct delimiters for the original matrix type.
      return delimiters[1] .. '\\begin{array}{' .. col_spec .. '}' .. matrix_content .. '\\end{array}' .. delimiters[2]
    end
    -- If no replacement is needed, return nil, and gsub will not perform a replacement.
    return nil
  end
 
  -- Iterate over all matrix types we know how to handle.
  for env_name, _ in pairs(matrix_delimiters) do
    -- This pattern is non-greedy `(.-)` and correctly handles nested structures
    -- because we are replacing from the inside out for each specific matrix type.
    math_text = string.gsub(math_text, '\\begin{' .. env_name .. '}(.-)\\end{' .. env_name .. '}', function(content)
      -- Call the sanitizer and if it returns a result, use it. Otherwise, reconstruct the original.
      return sanitize_matrix(env_name, content) or ('\\begin{' .. env_name .. '}' .. content .. '\\end{' .. env_name .. '}')
    end)
  end
 
  -- Update the element's text with the potentially modified LaTeX code.
  el.text = math_text
  -- Return the modified element to be placed back into the AST.
  return el
end