#!/usr/bin/env python
"""
  Copyright 2013 Thomas McGrew <tjmcgrew@gmail.com>

  This program is free software: you can redistribute it and/or modify it under 
  the terms of the GNU Affero General Public License as published by the Free 
  Software Foundation, either version 3 of the License, or (at your option) any 
  later version.

  This program is distributed in the hope that it will be useful, but WITHOUT 
  ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS 
  FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more 
  details.

  You should have received a copy of the GNU Affero General Public License along 
  with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ForkingMixIn
import os
import sys
import re
from cStringIO import StringIO
from optparse import OptionParser
import json
import random
import string


VERSION = "0.2"
UPLOAD_BUTTON = "uploadButton"
UPLOAD_FILE = "upload"

PROGRESS_HTML = """<!DOCTYPE html>
<html>
  <head>
    <title>Upload Progress</title>
    <style type="text/css">
      body {
        padding: 0;
        margin: 0;
        font-family: Arial, Helvetica, sans-serif;
      }
      #progress {
        width: 400px;
        height: 1.2em;
        border: 1px solid black;
        position: relative;
        text-align: center;
        overflow: hidden;
      }
      #progressbar {
        width: 0;
        height: 100%%;
        background-color: #66ff66;
        position: absolute;
        top: 0;
        left: 0;
        z-index: -1;
      }
      #fileBox {
        padding: 1em;
      }
      #progressIndicator {
        font-weight: bold;
      }
      .complete {
        font-size: 0.8em;
        color: #33aa33;
      }
      .inTransit {
        font-size: 0.8em;
        color: #dd4444;
      }
    </style>
  </head>
  <body>

<div id='progress'>
  <div id='progressbar'>
  </div>
  <span id='progressIndicator'>0%%</span>
</div>
<div id='fileBox'>
  <h3>Files:</h3>
  <span id='fileList'>
  </span>
</div>
<script src="//ajax.googleapis.com/ajax/libs/jquery/1.8.3/jquery.min.js">
</script>
<script><!--
  function updateProgress( ) {
    jQuery.getJSON( '%s', function( data ) {
      if ( data.read ) {
        if ( data.read == data.total ) {
          setTimeout( close, 3000 );
        }
        progressbar = jQuery( '#progressbar' );
        progressIndicator = jQuery( '#progressIndicator' );
        fileList = jQuery( '#fileList' );
        progressbar.css( 'width', data.read / data.total * 400 );
        progressIndicator.html( 
          Math.round( data.read / data.total * 100 ) + "%%")
        filesHTML = data.files.join( 
          ' <span class="complete">Complete!</span><br />');
        if ( data.files.length )
          filesHTML += ' <span class="complete">Complete!</span><br />';
        if ( data.current )
          filesHTML += 
            data.current + ' <span class="inTransit">Transferring...</span>';
        fileList.html( filesHTML );
      }
    });
  }
  $( function( ) {
    setInterval( updateProgress, 2000 );
  });
  --></script>
  </body>
</html>
"""

class ForkingServer(ForkingMixIn, HTTPServer):
  pass

class UploadHandler(BaseHTTPRequestHandler):
  upload_button = UPLOAD_BUTTON
  upload_file = UPLOAD_FILE

  def do_GET( self ):
    """
    Listens for a GET request and returns an upload form
    """
    self.rfile._sock.settimeout( 30 )
    self._parse_cookies( )
    self._preprocess_get( )
    self.progress_url = OPTIONS.url
    if self.progress_url.endswith( '/' ):
      self.progress_url = self.progress_url[ :-1 ]
    self.progress_url += '/progress'
    if OPTIONS.progress:
      if self.path == "/progress": 
        self._progress( )
        return
      if self.path == "/progress.html":
        self._get_progress_page( )
        return
    self._send_get_response( )

  def _progress( self ):
    if not OPTIONS.progress:
      self.send_error( 403 )
      return
    progressfilename = \
      os.sep.join([OPTIONS.tmp_folder, "progress", 
        self.cookies[OPTIONS.sessionkey]])
    if not os.path.exists( progressfilename ):
      self.send_error( 404 )
      return

    self.send_response( 200 )
    self.send_header( 'Content-Type', 'application/json' )
#    self.send_header( 'Content-Length', 
#      int( os.stat( progressfilename ).stat_size ))
    self.end_headers( )
    progressfile = open( progressfilename, 'r' )
    self.wfile.write( progressfile.read( ))
    progressfile.close( )
    self.wfile.close( )
    

  def _get_progress_page( self ):
    reply = PROGRESS_HTML % self.progress_url
    self.send_response( 200 )
    self.send_header( "Content-Type", 'text/html' )
    self.send_header( "Content-Length", len( reply ))
    self.end_headers( )
    self.wfile.write( reply )
    self.wfile.close( )

  def do_POST( self ):
    """
    Reads a post request from a web browser and parses the variables.
    """
    self.rfile._sock.settimeout( 30 )
    self.content_length = int( self.headers[ 'Content-Length' ])
    if ( self.content_length < 0 ):
      self.content_length += 0x100000000
    self.remaining_content = self.content_length
    self._parse_cookies( )
    self.upload_folder = OPTIONS.upload_folder
    if OPTIONS.progress:
      self._start_session( )
      progressdir = os.sep.join([OPTIONS.tmp_folder, "progress"])
      if not os.path.exists( progressdir ):
        os.makedirs( progressdir )
    self._preprocess_post( )
    self._read_post_data( )
    self._send_post_response( )

  def _start_session( self ):
    if not self.cookies.has_key( OPTIONS.sessionkey ):
      self._set_cookie(  OPTIONS.sessionkey,
        ''.join( random.choice( string.ascii_uppercase + string.digits ) 
        for i in range(32)))

  def _set_cookie( self, name, value, path='/' ):
    self.send_header( 'Set-Cookie', '%s=%s; Path=%s' % ( name, value, path ))

  def _parse_cookies( self ):
    """
    Reads the cookie information sent from the client and places it in 
    the self.cookies dict. If no cookie information has been sent, this dict 
    will be empty (length of 0).
    """
    # parse the cookies
    if self.headers.has_key( 'Cookie' ):
      cookie_pieces = re.split( "(.*?)=(.*?)(:?; |$)", self.headers['Cookie'] )
      self.cookies = dict( zip( cookie_pieces[1::4], cookie_pieces[2::4]))
    else:
      self.cookies = dict( )
    return self.cookies

  def _read_post_data( self ):
    """
    Parses the information in a POST request.
    """
    # read the separator token.
    token = self.rfile.readline( )
    self.remaining_content -= len(token)
    token = token.strip( )

    # read the post request
    self.buf = ''
    self.postdict = { 'files': [] }
    while self.remaining_content > 0 or len(self.buf):
      name, value_buffer = self._parse_post_item( token )
      if type( value_buffer ) is file:
        self.log_message( "Saved file %s", value_buffer.name )
        value = value_buffer.name
        self.postdict['files'].append( value )
        if OPTIONS.progress:
          self._update_progress( )
      else:
        value = value_buffer.getvalue( )

      if self.postdict.has_key( name ):
        if type(self.postdict[ name ]) is str:
          self.postdict[ name ] = [ self.postdict[ name ], value ]
        else:
          self.postdict[ name ].append( value )
      else:
        self.postdict[ name ] = value
      value_buffer.close( )
      if type( value_buffer ) is file:
        self._postprocess_upload( value )

  def _postprocess_upload( self, filename ):
    """
    File upload post-processing. By defualt this method does nothing, override
    it if you would like to perform some operation on each file that is
    uploaded.

    :Parameters:
      filename : string
        The path to the file which has just completed uploading.
    """
    pass

  def _preprocess_get( self ):
    """
    GET request pre-processing. By default this method does nothing, override
    it to perform some tasks before processing of the request.
    """
    pass

  def _preprocess_post( self ):
    """
    POST request pre-processing. By default this method does nothing, override
    it to perform some tasks before processing of the request.
    """
    pass

  def _send_get_response( self ):
    self.send_response( 200 )
    if OPTIONS.progress:
      self._start_session( )
    self.send_header( 'Content-Type', 'text/html' )
    self.end_headers( )
    self.wfile.write( """<!DOCTYPE html>
      <html>
        <head>
        </head>
        <body>
          <form method="post" name="fileUpload" action="%s" 
          enctype="multipart/form-data">
            <input type="file" name="%s" multiple="true"/><br />
            <button id='upload' type="submit" name="%s" value="true">Upload</button>
          </form>
        """ % ( OPTIONS.url, self.upload_file, self.upload_button ))
    if OPTIONS.progress:
      self.wfile.write( """
        <script 
          src="//ajax.googleapis.com/ajax/libs/jquery/1.8.3/jquery.min.js">
        </script>
        <script><!--
          $(function( ) {
            jQuery( '#upload' ).click( function( ) {
              jQuery('*').css( 'cursor','wait');
              if ( ! jQuery.browser.msie ) // progress bar doesn't work in IE.
                open( '%s.html', '',
                  'width=402,height=400,titlebar=no,toolbar=no,status=no,' +
                  'menubar=no,location=no' );
            });
          });
        --></script>""" % ( self.progress_url ))
    self.wfile.write( "</body></html>" )

  def _send_post_response( self ):
    self.send_response( 200 )
    if OPTIONS.progress:
      self._start_session( )
    self.send_header( 'Content-Type', 'text/html' )
    self.end_headers( )
    self.wfile.write( "<!DOCTYPE html><html><head></head><body>" )
    self.wfile.write( "Upload Complete" )
    self.wfile.write( "</body>" )
    self.wfile.close( )


  def _parse_post_item( self, token ):
    """
    Parses out a single item from a post request.

    :Parameters:
      token : string
        The separator token for each post variable

    rtype: tuple
    return: A tuple containing the name of the variable and the buffer 
    containing it's value. This could either be a file object or a StringIO
    object.
    """
    name = None
    filename = None
    line = self._next_line( )
    nameheader = re.search( 
      'Content-Disposition: form-data; name="(.*?)"', line )
    if nameheader:
      name = nameheader.group(1)
    fileheader = re.search( 'filename="(.*?)"', line )
    if fileheader:
      filename = fileheader.group( 1 )
      if os.sep in filename:
        filename = filename[ filename.rfind( os.sep ): ]

    while len(line.strip()):
      line = self._next_line( )

    if filename:
      if not os.path.exists( self.upload_folder ):
        os.makedirs( self.upload_folder )
      value_buffer = open( '%s/%s' % ( self.upload_folder, filename), 'wb' )
    else:
      value_buffer = StringIO( )
    prev_line = False
    while not line.startswith( token ):
      line = self._next_line( )
      if line.startswith( token ):
        value_buffer.write( prev_line[:-2] )# strip the "^M\n" from the end
        break
      if not ( prev_line is False ):
        value_buffer.write( prev_line )
      prev_line = line
      if OPTIONS.progress:
        # update the upload progress
        self._update_progress( filename )
    return ( name, value_buffer )

  def _next_line( self ):
    """
    Reads the next line of text from the post buffer and returns it.

    rtype: string
    return: The next line in the post data buffer
    """
    if self.remaining_content > 0 and len(self.buf) < OPTIONS.buf_size \
      and not '\n' in self.buf:
      self.buf += self.rfile.read( 
        OPTIONS.buf_size if self.remaining_content > OPTIONS.buf_size
        else self.remaining_content )
      self.remaining_content -= OPTIONS.buf_size
    line = self.buf[ :self.buf.find('\n')+1 
      if '\n' in self.buf else len(self.buf)] 
    self.buf = self.buf[len(line):]
    return line

  def _update_progress( self, current_transfer=None ):
    """
    Adds uploaded files and current upload progress to a file for the JSON 
    progress feed.
    """
    # create a file with a different name and rename it. This should prevent the
    # progress feed thread from sending an incomplete file.
    progressfilename = os.sep.join([OPTIONS.tmp_folder, "progress", 
        self.cookies[OPTIONS.sessionkey]])
    progressfile = open( progressfilename + '~', 'w')
    progress = { 'files': [os.path.basename( x ) for x in self.postdict[ 'files' ]], 
      'read': (( self.content_length - self.remaining_content )
        if self.remaining_content > 0 else self.content_length ),
      'total': self.content_length }
    if current_transfer:
      progress['current'] = current_transfer
    progressfile.write( json.dumps( progress ))
    progressfile.close( )
    os.rename( progressfilename + '~', progressfilename )


optParser = OptionParser(version="%%prog %s" % VERSION, usage="%prog [options]")
optParser.add_option( "-a", "--address", dest="address", default="",
  help="The ip address for the server to listen on" )
optParser.add_option( "--buffer-size", dest="buf_size", type="int", default=8,
  help="Specify the buffer size for post request (in KB)." )
optParser.add_option( "-f", "--form-path", dest="url", default="/",
  help="The path to the upload form on the server. Useful if the server is "
       "behind a proxy" )
optParser.add_option( "-p", "--port",  dest="port", type="int", default=8000,
  help="Specify the port for the server to listen on" )
optParser.add_option( "-u", "--upload-location", dest="upload_folder", 
  default="/tmp", help="The location to store uploaded files" )
optParser.add_option( "-t", "--tmp-location", default="/tmp", dest="tmp_folder",
  help="The location to store temporary files for the progress feed, etc." )
optParser.add_option( "--enable-progress", action="store_true", 
  dest="progress", default=False,
  help="Enable progress JSON feed for monitoring upload progress" )
optParser.add_option( "--session-key", dest="sessionkey", 
  default="UploadSession",
  help="The name of the cookie to be used for identifying users" )

def main( handler=UploadHandler ):
  global OPTIONS
  sys.stderr.write( "Starting with command: %s\n" % ' '.join( sys.argv ))
  OPTIONS, args = optParser.parse_args( )
  OPTIONS.buf_size *= 1024
  httpd = ForkingServer(( OPTIONS.address, OPTIONS.port ), handler )
  httpd.serve_forever( )


if __name__ == "__main__":
  main( ) 
