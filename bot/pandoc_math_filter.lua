-- pandoc_math_filter.lua
-- A Pandoc Lua filter to sanitize math environments, specifically for fixing
-- matrix environments like 'pmatrix' that contain '\hline', which is invalid syntax.

-- This function is the core of the filter. It's called for each 'Math' element
-- in the Pandoc Abstract Syntax Tree (AST).
function Math(el)
  -- el.text contains the raw LaTeX code of the math element.
  local math_text = el.text

  -- This is a generic replacer function. It takes the name of a matrix environment
  -- (like 'pmatrix') and its content.
  local function sanitize_matrix(env_name, content)
    -- We only intervene if the content of the matrix contains '\hline'.
    if content:find('\\hline') then
      -- If '\hline' is found, we must convert the environment to 'array',
      -- which supports '\hline'.

      -- To create a valid 'array', we need to know the number of columns.
      -- We determine this by finding the line with the most alignment tabs ('&').
      local max_cols = 0
      for line in content:gmatch("[^\\\\]+") do -- Split by '\\'
        local clean_line = line:gsub('%s*\\hline%s*', '') -- Ignore \hline lines for counting
        if #clean_line > 0 then
          local cols = 1 + select(2, clean_line:gsub('&', ''))
          if cols > max_cols then
            max_cols = cols
          end
        end
      end

      -- Construct the column specification string, e.g., 'ccc' for 3 columns.
      local col_spec = string.rep('c', max_cols)
      -- Return the new LaTeX code, wrapping the array in appropriate delimiters.
      return '\\left(\\begin{array}{' .. col_spec .. '}' .. content .. '\\end{array}\\right)'
    end
    -- If '\hline' is not found, we return nil, which tells gsub to not replace anything.
    return nil
  end

  -- We use string.gsub with a function to find and replace all pmatrix environments.
  -- The pattern captures the environment name and its content.
  -- The 'sanitize_matrix' function is called for each match.
  math_text = string.gsub(math_text, '\\begin{pmatrix}(.-)\\end{pmatrix}', function(content)
    return sanitize_matrix('pmatrix', content)
  end)

  -- Update the element's text with the potentially modified LaTeX code.
  el.text = math_text
  -- Return the modified element to be placed back into the AST.
  return el
end