#!/usr/bin/env ruby

["debug", "info", "warning", "warn", "exception", "error", "critical"].each do |level|
  # Try to automatically clean up a bit first
  system(%{for F in `find . -name "*py"`; do  sed -E 's/(\.#{level}\(".*")[ ]*%/\1,/g' $F; done})
  system(%{for F in `find . -name "*py"`; do  sed -E "s/(\.#{level}\('.*')[ ]*%/\1,/g" $F; done})
  # Now examine each line by hand
  `git grep -n '\.#{level}(' | cut -d ':' -f1,2  | sed "s/:/ +/g"`.each_line do |line|
    system("vim #{line}")
  end
end
