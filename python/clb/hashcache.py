#!/usr/bin/env python3

# Copyright [2026] [Christopher Brealey]
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# --------------------------------------------------------------------
# Usage: python hashcache.py [-c cachefile] [pathname...]
#
# This program computes MD5 checksums of files, but it also maintains
# an on-disk cache of the checksums. The program returns the cached
# hash of a file provided that the file's length (in bytes) and last
# update timestamp (in seconds since epoch) match what's recorded in
# the cache (a "cache hit"). If there is a cache miss, either because
# the filename isn't recorded in the cache, or it is but the length
# or last update timstamp differ from those of the actual file, then
# the program computes the hash from the file and updates the cache.
# The cache is persisted as a single JSON file. The file is loaded
# at the beginning of the program, then saved in-place at the end.
# Because the load and save operations may be time consuming, it is
# best to maximize the number of file pathname arguments passed to a
# single run of the program.
#
# The default cache file is /tmp/hashcache.json.
# The -c option is used to specify a cache file.
#
# If environment variable DEBUG is set to anything, the program
# displays debug information to stderr as it runs.
#
# The cache is represented in memory as a Python 'dict', and on disk
# as JSON. The cache consists of two top level objects: 'metadata'
# and 'index'. The 'metadata' object contains information about the
# cache, such as the hash algorithm, and the way relative pathnames
# are indexed. The 'index' object contains the list of cached path
# names, each path name the key to its last known file length, file
# update timestamp, and hash.
# --------------------------------------------------------------------

import sys
import os
import json
import hashlib
import argparse

DEBUG = os.environ.get('DEBUG')
DEFAULT_CACHE_FILEPATH = "/tmp/hashcache.json"
DEFAULT_HASH_ALGORITHM = "md5"
DEFAULT_ABSOLUTE_PATHS = False

# --------------------------------------------------------------------
# Displays a debug message to stderr, if the DEBUG environment
# is set to anything.
# --------------------------------------------------------------------

def debug(msg):
    if DEBUG != None:
        print(f"DEBUG: {msg}", file=sys.stderr)

# --------------------------------------------------------------------
# Each object of this class represents an instance of a cache backed
# by a specific cache filename. Do not instantiate multiple instances
# backed by the same cache file. The results are likely undesirable.
# When instantiating a HashCache, you can override the default cache
# file pathname, the hash algorithm, and relative pathname handling.
# The cache file pathname can be changed using set_cache_filepath().
# The other properties can be altered when clearing the cache, and
# are updated when loading a cache. In other words, cache metadata
# cannot be altered once data is loaded into the cache index.
# --------------------------------------------------------------------

class HashCache:

    # --------------------------------------------------------------------
    # Instantiates an instance of the cache. Although the method captures
    # the cache filename, the file system is not accessed at this time.
    # Only the load_cache() and save_cache() methods do that.
    # --------------------------------------------------------------------

    def __init__(self, cache_filepath=DEFAULT_CACHE_FILEPATH, hash_algorithm=DEFAULT_HASH_ALGORITHM, absolute_paths=DEFAULT_ABSOLUTE_PATHS):
        self.cache_filepath = cache_filepath
        self.clear(hash_algorithm, absolute_paths)
        debug(f"__init__(): cache_filepath={self.cache_filepath} hash_algorithm={self.hash_algorithm} absolute_paths={self.absolute_paths}")

    # --------------------------------------------------------------------
    # Clears, or effectively initializes, the in-memory cache. The core
    # of the cache is "index", a dict of file metadata keyed by pathname.
    # Additional in memory variables "hashAlgorithm" and "absolutePaths"
    # duplicate information in the index metadata, but are defined so
    # that get_full_spec_fs() isn't spending time dereferencing the
    # "metadata" dict and its children.
    # --------------------------------------------------------------------

    def clear(self, hash_algorithm=DEFAULT_HASH_ALGORITHM, absolute_paths=DEFAULT_ABSOLUTE_PATHS):
        self.hash_algorithm = hash_algorithm
        self.absolute_paths = absolute_paths
        self.cache = {
            "metadata": {
                "hashAlgorithm": self.hash_algorithm,
                "absolutePaths": self.absolute_paths
            },
            "index": {}
        }
        self.index = self.cache["index"]
        debug(f"clear(): cache_filepath={self.cache_filepath} hash_algorithm={self.hash_algorithm} absolute_paths={self.absolute_paths} cache={self.cache}")

    # --------------------------------------------------------------------
    # Returns a deep copy of the cache index.
    # --------------------------------------------------------------------

    def get_index(self):
        debug(f"get_index()")
        return self.index.deepcopy()

    # --------------------------------------------------------------------
    # Returns the cache file pathname.
    # This method does not interact with the file system.
    # --------------------------------------------------------------------

    def get_cache_filepath(self):
        debug(f"get_cache_filepath(): cache_filepath={self.cache_filepath}")
        return self.cache_filepath

    # --------------------------------------------------------------------
    # Sets the cache file pathname.
    # This method does not interact with the file system.
    # --------------------------------------------------------------------

    def set_cache_filepath(self,filepath):
        debug(f"set_cache_filepath(): filepath={filepath}")
        self.cache_filepath = filepath

    # --------------------------------------------------------------------
    # Returns the hash algorithm.
    # --------------------------------------------------------------------

    def get_hash_algorithm(self):
        debug(f"get_hash_algorithm(): hash_algorithm={self.hash_algorithm}")
        return self.hash_algorithm

    # --------------------------------------------------------------------
    # Returns the absolute path setting.
    # --------------------------------------------------------------------

    def get_absolute_paths(self):
        debug(f"get_absolute_paths(): absolute_paths={self.absolute_paths}")
        return self.absolute_paths

    # --------------------------------------------------------------------
    # Clears the in-memory index, then loads the cache from the file as
    # named by get_cache_filepath().
    # --------------------------------------------------------------------

    def load_cache(self):
        self.cache["index"] = {}
        self.index = self.cache["index"]
        try:
            with open(self.cache_filepath, 'r') as f:
                self.cache = json.load(f)
                self.index = self.cache["index"]
                self.hash_algorithm = self.cache["metadata"]["hashAlgorithm"]
                self.absolute_paths = self.cache["metadata"]["absolutePaths"]
        except Exception as e:
            debug(f"load_cache(): exception e={e}")
        finally:
            debug(f"load_cache(): cache_filepath={self.cache_filepath} len(index)={len(self.index)} cache_filepath={self.cache_filepath} hash_algorithm={self.hash_algorithm} absolute_paths={self.absolute_paths}")

    # --------------------------------------------------------------------
    # Saves the cache to the file as named by get_cache_filepath().
    # --------------------------------------------------------------------

    def save_cache(self):
        debug(f"save_cache(): cache_filepath={self.cache_filepath} len(index)={len(self.index)} cache_filepath={self.cache_filepath} hash_algorithm={self.hash_algorithm} absolute_paths={self.absolute_paths}")
        try:
            with open(self.cache_filepath, 'w') as f:
                json.dump(self.cache, f)
        except Exception as e:
            debug(f"save_cache(): exception e={e}")

    # --------------------------------------------------------------------
    # Returns the timestamp, length, and MD5 hash of the contents of the
    # given file. This method consults the cache first. If a cache entry
    # is present with a timestamp that matches that of the file, the
    # method returns the timestamp, length, and MD5 hash from the cache.
    # Otherwise, the method re-computes the length and MD5 hash of the
    # file and updates the cache.
    # --------------------------------------------------------------------

    def get_full_spec(self,filepath):
        spec = self.get_full_spec_cache(filepath)
        if spec == None:
            spec = self.get_full_spec_fs(filepath)
            debug(f"get_full_spec(): MISS: filepath={filepath} spec={spec}")
            if spec != None:
                debug(f"get_full_spec(): MISS: NEW")
                self.index[filepath] = spec
        else:
            simple = self.get_simple_spec_fs(filepath)
            debug(f"get_full_spec(): HIT: filepath={filepath}")
            if simple == None:
                debug(f"get_full_spec(): HIT: DELETED")
                spec = None
                self.index.pop(filepath, None)
            elif spec["ts"] != simple["ts"] or spec["len"] != simple["len"]:
                debug(f"get_full_spec(): HIT: STALE")
                spec = self.get_full_spec_fs(filepath)
                self.index[filepath] = spec
            else:
                debug("HIT: MATCH")
        return spec

    # --------------------------------------------------------------------
    # Returns the timestamp, length, and MD5 hash of the contents of the
    # given file according to the cache, or None if there is no entry.
    # --------------------------------------------------------------------

    def get_full_spec_cache(self,filepath):
        try:
            return self.index[filepath]
        except Exception as e:
            return None

    # --------------------------------------------------------------------
    # Returns the timestamp, length, and MD5 hash of the contents of the
    # given file on the file system. Returns None if the file does not
    # exist.
    # --------------------------------------------------------------------

    def get_full_spec_fs(self,filepath):
        try:
            algorithm = hashlib.new(self.hash_algorithm)
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    algorithm.update(chunk)
            spec = {
                "ts": os.path.getmtime(filepath),
                "len": os.path.getsize(filepath),
                "hash": algorithm.hexdigest()
            }
            return spec
        except Exception as e:
            return None

    # --------------------------------------------------------------------
    # Returns the timestamp and length of the contents of the given file
    # on the file system. Returns None if the file does not exist.
    # --------------------------------------------------------------------

    def get_simple_spec_fs(self,filepath):
        try:
            spec = {
                "ts": os.path.getmtime(filepath),
                "len": os.path.getsize(filepath)
            }
            return spec
        except Exception as e:
            return None

# --------------------------------------------------------------------
# Main: Loads the cache of file hashes, displays a line of the format
# "<HASH> <FILEPATH>" for each file named listed in the arguments and
# that exists, then saves the cache. 
# --------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-c', '--cache', default=DEFAULT_CACHE_FILEPATH)
    parser.add_argument('-a', '--algorithm', default=DEFAULT_HASH_ALGORITHM)
    parser.add_argument('pathnames', nargs='*')
    args = parser.parse_args()
    debug(f"main(): args.cache={args.cache}")
    debug(f"main(): args.pathnames={args.pathnames}")
    hashcache = HashCache(args.cache,hash_algorithm=args.algorithm)
    hashcache.load_cache()
    for f in args.pathnames:
        spec = hashcache.get_full_spec(f)
        if spec != None:
            h = spec["hash"]
            print(f"{h} {f}")
    hashcache.save_cache()

if __name__ == "__main__":
    main()
