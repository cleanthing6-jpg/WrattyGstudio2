#!/bin/bash

echo "Big Max Zero Installer"
echo "======================"
echo ""

# Create plugin directories if they don't exist
mkdir -p ~/.vst3
mkdir -p ~/.clap

# Install VST3
if [ -d "Big Max Zero.vst3" ]; then
    cp -r "Big Max Zero.vst3" ~/.vst3/
    echo "✓ VST3 installed to ~/.vst3/"
else
    echo "✗ VST3 not found"
fi

# Install CLAP
if [ -f "Big Max Zero.clap" ]; then
    cp "Big Max Zero.clap" ~/.clap/
    echo "✓ CLAP installed to ~/.clap/"
else
    echo "✗ CLAP not found"
fi

echo ""
echo "Done! Restart your DAW to load the plugins."
