import configparser
import os
import sqlite3
import tkinter
import glob
from pprint import pprint
from zlib import crc32
from tqdm import tqdm
from tkinter import ttk, font

# globals
CONFIG_FILE = 'filedb.ini'
DATABASE = 'filedb.db'

# Scrollable treeview, to add horizontal and vertical scrolling to the tree view
class ScrollableTreeView(tkinter.Frame):
  def __init__(self, parent, width, **kwargs):
    # initalize this object to have the same properties as an
    # initalized tk.Frame
    # and initialize the frame with respect to the parent tkinter object
    super().__init__(parent, width=width)
    
    # stops treeview from expanding the containing frame
    self.pack_propagate(0)
    self.grid_propagate(0)
    
    # needed for proper reactive UI resizing
    self.grid_rowconfigure(0, weight=1)
    self.grid_columnconfigure(1, weight=1)
    
    tree = ttk.Treeview(self, **kwargs)
    tree.grid(row=0, column=1, sticky='nsew')
    
    # set up vertical scrollbar to scroll the treeview
    scrolly = tkinter.Scrollbar(self, command=tree.yview)
    scrolly.grid(row=0, column=0, sticky='nsw') # won't auto-expand because column isn't configured with a weight
    tree.config(yscrollcommand=scrolly.set) # sets the scrollbar to match where the text is scrolled to
    
    # set up horizontal scrollbar to scroll the treeview
    scrollx = tkinter.Scrollbar(self, command=tree.xview, orient='horizontal')
    scrollx.grid(row=1, column=1, sticky='sew') # won't auto-expand because column isn't configured with a weight
    tree.config(xscrollcommand=scrollx.set) # sets the scrollbar to match where the text is scrolled to
    
    self.heading = tree.heading
    self.column = tree.column
    self.bind = tree.bind
    self.delete = tree.delete
    self.get_children = tree.get_children
    self.insert = tree.insert
    self.item = tree.item
    self.selection_set = tree.selection_set
    self.selection = tree.selection
    self.parent = tree.parent
    self.identify = tree.identify
    self.selection_remove = tree.selection_remove
    self.configure = tree.configure
    self.xview = tree.xview

class FileDB:
  def __init__(self, db_path, start_dir):
    self.con = sqlite3.connect(db_path)
    self.currentDir = start_dir
    self.IterateDirAddFiles()
  
  def __del__(self):
    self.con.close()
  
  def SlowReadData(self, filepath):
    with open(filepath, 'rb') as fi:
      yield fi.read(1024)
  
  def RunSQLCommit(self, sql):
    cur = self.con.cursor()
    cur.execute(sql)
    self.con.commit()
  
  def RunSQLGet(self, sql):
    cur = self.con.cursor()
    return cur.execute(sql)
  
  def RunSQLGetSingleRow(self, sql):
    cur = self.con.cursor()
    return cur.execute(sql).fetchone()
  
  def PrintTable(self, tablename):
    cur = self.con.cursor()
    table_res = cur.execute("PRAGMA table_info('" + tablename + "')")
    returned_data = [[]]
    for column in table_res:
      returned_data[0] += [column[1]]
      #print(f"{column[1]}({column[2]})", end='')
    #print('')
    row_res = cur.execute('select * from ' + tablename + ' limit 10')
    for row in row_res:
      returned_data += [list(row)]
      #print('\t\t\t'.join([str(x) for x in row]))
    
    # figure out how many spaces are needed to line stuff up
    longest_cols = []
    for row in returned_data:
      for i, col in enumerate(row):
        if len(longest_cols) <= i:
          longest_cols += [0]
        col = str(col) + ' ' # minimum of 1 space
        if len(col) > longest_cols[i]:
          longest_cols[i] = len(col)
    
    # print with the right amount of spaces between columns to line stuff up, up to the biggest needed
    for row in returned_data:
      for i, col in enumerate(row):
        col = str(col)
        col_print_len = len(col)
        needed_len = longest_cols[i] - col_print_len
        
        print(col, end='')
        for j in range(needed_len):
          print(' ', end='')
      
      print('')
    #print(longest_cols)
  
  def CheckTableExists(self, tablename):
    return True if self.RunSQLGet("select count(1) from sqlite_master where type='table' and name='ChecksumTypes'").fetchone()[0] > 0 else False
    
  
  # add a file to the database by path
  # if the table for files isn't created yet, create it
  def AddFileToDB(self, filepath):
    if not self.CheckTableExists("ChecksumTypes"):
      self.RunSQLCommit("create table ChecksumTypes (chkid integer primary key, chkname text)")
      self.RunSQLCommit("insert into ChecksumTypes values (NULL, 'Adler32')")
      self.RunSQLCommit("insert into ChecksumTypes values (NULL, 'CRC32')")
      self.RunSQLCommit("insert into ChecksumTypes values (NULL, 'MD5')")
    
    self.RunSQLCommit("create table if not exists Files (fileid integer primary key, filepath text, filechksum_type integer, filechksum text, additional_fields blob)")
    
    #print(filepath)
    
    last_crc32 = 0
    for byte in self.SlowReadData(filepath):
      last_crc32 = crc32(byte, last_crc32)
    
    #print(last_alder32)
    self.RunSQLCommit(f"insert into Files values (NULL, '{filepath}', 2, '{last_crc32}', NULL)")
  
  def IsFileInDB(self, filepath):
    return 1 if self.RunSQLGetSingleRow(f"select * from Files where filepath='{filepath}'") != None else 0
  
  def GetFileId(self, filepath):
    fileid = self.RunSQLGetSingleRow(f"select * from Files where filepath='{filepath}'")[0]
    return fileid
  
  def AddTagToFile(self, tagname, filepath):
    self.RunSQLCommit('create table if not exists Tags (tagid integer primary key, tagname text)')
    self.RunSQLCommit('create table if not exists TagMappings (tagid integer, fileid integer)')
    
    if self.RunSQLGetSingleRow(f"select * from Tags where tagname='{tagname}'") == None:
      self.RunSQLCommit(f"insert into Tags values (NULL, '{tagname}')")
    
    tagid = self.RunSQLGetSingleRow(f"select * from Tags where tagname='{tagname}'")[0]
    
    
    self.RunSQLCommit(f"insert into TagMappings values ({tagid}, {self.GetFileId(filepath)})")
  
  def AutoTagFile(self, filepath):
    extension = os.path.splitext(filepath)[-1]
    
    self.AddTagToFile(extension, filepath)
  
  #def AutoTagFileDirectory(self, directory):
    
  
  def IterateDirAddFiles(self):
    fileList = glob.glob(os.path.join(self.currentDir, '*.*'))[0:2]
    
    for file in tqdm(fileList, ncols=150):
      if not self.CheckTableExists('Files'):
        self.AddFileToDB(file)
      if not self.IsFileInDB(file):
        self.AddFileToDB(file)
      
      self.AutoTagFile(file)
    
    #self.AutoTagFile(fileList[1])
    
    self.PrintTable('Tags')
    #print(self.IsFileInDB(fileList[0]))
    
class FileUI:
  def __init__(self, fdb, startpath):
    self.filedb = fdb
    #print(file_list)
    
    
    self.tk = tkinter.Tk()
    self.tk.title('FileDB')
    self.tk.geometry('800x600')
    
    self.tkinter_font = tkinter.font.Font(family='Consolas', size=12)
    ttk.Style().configure('Treeview', font=self.tkinter_font)
    
    
    encompassingFrame = tkinter.Frame(self.tk)
    encompassingFrame.pack(fill='both', expand=True)
    
    frame1 = tkinter.Frame(encompassingFrame)
    frame1.pack(anchor='sw', fill='both', expand=True)
    
    self.tree1 = ScrollableTreeView(frame1, 300, selectmode='browse')
    self.tree1.pack(anchor='w', side='left', fill='y', expand=True)
    self.tree1.heading('#0', text=startpath)
    self.tree1.column('#0', anchor='w')
    
    #frame2 = tkinter.Frame(encompassingFrame)
    #frame2.pack(anchor='se', fill='y', expand=True)
    
    self.tree2 = ScrollableTreeView(frame1, 300, selectmode='browse')
    self.tree2.pack(anchor='e', side='right', fill='y', expand=True)
    self.tree2.heading('#0', text=startpath)
    self.tree2.column('#0', anchor='w')
    
    self.PopulateTreeView(self.tree1, [['', '..']] + list(self.filedb.RunSQLGet(f"select * from Files where filepath like '{startpath}%'")))
    
    self.PopulateTreeView(self.tree2, [['', '..']] + list(self.filedb.RunSQLGet(f"select * from Files where filepath like '{startpath}%'")))
    
    self.tagSearchBox = tkinter.Entry(self.tk)
    self.tagSearchBox.pack()
    tkinter.Button(self.tk, text='Search By Tag', command=self.SearchByTag).pack()
    self.tk.mainloop()
  
  # populate a treeview from a list
  def PopulateTreeView(self, tree, li):
    biggest_node_width = 0
    
    for row in li:
      tree.insert('', 'end', text=row[1])
      if len(row[1]) > biggest_node_width:
        tree.column('#0', anchor='w', width=self.tkinter_font.measure(row[1]) + 25, stretch=False)
        biggest_node_width = len(row[1])
  
  def SearchByTag(self):
    popup = tkinter.Toplevel()
    popup_frame = tkinter.Frame(popup)
    popup_frame.pack()
    popup_tree = ScrollableTreeView(popup_frame, 300, selectmode='browse')
    popup_tree.pack()
    tkinter.Label(popup, text='Results:').pack()
    for row in self.filedb.RunSQLGet(f"select * from Files inner join TagMappings on Files.fileid=TagMappings.fileid inner join Tags on TagMappings.tagid=Tags.tagid where Tags.tagname='{self.tagSearchBox.get()}'"):
      popup_tree.insert('', 'end', text=row[1])
      #tkinter.Label(popup, text=row[1]).pack()
      #tkinter.Label(self.tk, text=row[1]).pack()

config = configparser.ConfigParser()

if os.path.exists(CONFIG_FILE):
  config.read(CONFIG_FILE)
else:
  config['Options'] = {'Path': os.getcwd()}
  with open(CONFIG_FILE, 'w') as configfile:
    config.write(configfile)

with open(DATABASE, 'w') as fi:
  fi.write('')

fdb = FileDB(DATABASE, config['Options']['Path'])

FileUI(fdb, config['Options']['Path'])