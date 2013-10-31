all:
	jekyll build
	cp _site/*html .

push:
	git commit -a -m "New Build"
	git push
