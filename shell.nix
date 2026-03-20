{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  buildInputs = [
    pkgs.gcc
    pkgs.xz.dev       # provides lzma.h and liblzma
    pkgs.pkg-config
  ];
}
