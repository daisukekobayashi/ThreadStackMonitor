namespace py tsm


struct Thread {
  1: required i32 id,
  2: optional binary name,
  3: optional i32 stack_size,
}


struct Process {
  1: required i32 id,
  2: optional binary name,
  3: optional binary path,
  4: optional i32 num_threads,
  5: optional list<Thread> thread,
}


service TSMonitor {
  i32 ping(),
  i32 refresh(),
  Process process(1: i32 id),
}
