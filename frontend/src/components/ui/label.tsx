import * as React from "react"

import { cn } from "@/lib/utils"

function Label({ className, ...props }: React.ComponentProps<"label">) {
  return (
    <label
      data-slot="label"
      className={cn("text-[11px] font-medium tracking-wide text-muted-foreground uppercase", className)}
      {...props}
    />
  )
}

export { Label }
