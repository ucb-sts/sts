#!/usr/bin/env ruby

require 'set'
require 'fileutils'

# Find all authors with: `git log --all --format='%aN' | sort | uniq`
# This script will raise an exception if not all authors are listed in this
# hash.
author2copyright = {
  'colin-scott' => 'Copyright 2011-2013 Colin Scott',
  'Colin' => 'Copyright 2011-2013 Colin Scott',
  'Colin Scott' => 'Copyright 2011-2013 Colin Scott',
  'rcs' => 'Copyright 2011-2013 Colin Scott',
  'Andreas Wundsam' => 'Copyright 2011-2013 Andreas Wundsam',
  'Sam Whitlock' => 'Copyright 2012-2013 Sam Whitlock',
  'Andrew Or' => 'Copyright 2012-2013 Andrew Or',
  'andrew-or' => 'Copyright 2012-2013 Andrew Or',
  'Eugene Huang' => 'Copyright 2012-2013 Eugene Huang',
  'Kyriakos Zarifis' => 'Copyright 2012-2012 Kyriakos Zarifis',
  'zarifis' => 'Copyright 2012-2012 Kyriakos Zarifis',
  'Aurojit Panda' => ''
}

# TODO(cs): should use ruby's directory walk. oh well
`find . -name "*py"`.each_line do |file|
  file.chomp!
  puts "Examining #{file}"
  # Get the committers
  committers = Set.new
  `git log --format='%aN' #{file}`.each_line do |author|
    author.chomp!
    raise if not author2copyright.include? author
    committers.add author2copyright[author]
  end

  # Now find the beginning of the header, and prepend the copyrights
  File.open("/tmp/buf", "w") do |buffer|
    File.foreach(file) do |line|
      if line =~ /Licensed under the Apache License, Version 2.0/
        committers.each do |committer|
          buffer.puts "# #{committer}"
        end
        buffer.puts "#"
      end
      buffer.puts line
    end
  end

  # Now replace the current file with the buffer
  FileUtils.mv("/tmp/buf", file)
end
