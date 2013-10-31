all:
	jekyll build

push:
	git commit -a -m "New Build"
	git push
