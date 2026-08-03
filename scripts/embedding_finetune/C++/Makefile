CXX      := g++
CXXFLAGS := -std=c++23 -O2 -Wall -Wextra -Wpedantic
TARGET   := build_triplets

all: $(TARGET)

$(TARGET): build_triplets.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

clean:
	rm -f $(TARGET)

.PHONY: all clean