#!/usr/bin/env ruby

input_file = ARGV.shift
input = File.open(input_file)

while line = input.gets
  if line =~ /^c.*OF Message START/
    line = input.gets
    while line !~ /OF Message END/
      puts line if line =~ /^c/ and line !~ /xid:/
      line = input.gets
    end
  end
end
