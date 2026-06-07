.PHONY: build test clean install

build:
	go build -o worktrail ./cmd/worktrail

test:
	go vet ./...
	go build ./...

clean:
	rm -f worktrail

install: build
	cp worktrail $$HOME/.local/bin/worktrail
